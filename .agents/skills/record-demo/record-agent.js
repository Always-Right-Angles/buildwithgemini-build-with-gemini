#!/usr/bin/env node
/**
 * record-agent.js — Record a screen-capture demo of your agent's chat UI.
 *
 * Drives a chat web UI with Playwright: opens the page, types each query,
 * waits for the reply, and saves a .webm video of the whole session. Works
 * against BOTH lab UIs:
 *   - the custom FastAPI chat frontend (default, http://localhost:8080)
 *   - the ADK Playground / dev UI (pass --app <name> or a full --url)
 *
 * It also overlays a branded "Gemini World Tour" frame on the recording and can
 * speed the final video up (via ffmpeg) so demos stay short and snappy.
 *
 * Nothing in here is specific to any one agent — point it at your UI and pass
 * the queries you want to demo.
 *
 * Examples:
 *   node record-agent.js -q "What can you do?" -q "Show me what's in stock"
 *   node record-agent.js --url http://localhost:8080 -o my_demo.webm -q "Hi"
 *   node record-agent.js --app my_agent -q "Tell me a joke"   # ADK dev UI
 *   node record-agent.js -q "Generate an image of a potion" --wait 30000 --speed 1.5
 */
const path = require('path');
const fs = require('fs');
const { execSync } = require('child_process');

// --- Resolve (and if needed, install) Playwright + its Chromium browser ------
//
// Playwright is expected to be installed ONCE, GLOBALLY (`npm install -g
// playwright`) — in the lab image, or by the one-time fallback below — so it's
// never written into each participant's repo. The Chromium binary lives in a
// shared per-user cache (e.g. ~/.cache/ms-playwright), so it's global too.

// Adds the global npm root to Node's module search path so `require('playwright')`
// finds a globally-installed copy. Returns true if the root was found.
function addGlobalModulePath() {
  try {
    const globalRoot = execSync('npm root -g', { encoding: 'utf8' }).trim();
    if (globalRoot && fs.existsSync(globalRoot) && !module.paths.includes(globalRoot)) {
      module.paths.unshift(globalRoot);
    }
    return !!globalRoot;
  } catch (e) {
    return false;
  }
}

function requirePlaywright() {
  addGlobalModulePath();
  return require('playwright').chromium; // throws if not resolvable
}

function loadChromium() {
  // 1. Already resolvable (local dir, global root, or NODE_PATH)?
  try {
    return requirePlaywright();
  } catch (e) { /* fall through to install */ }

  // 2. Install globally, once. Falls back to a local install only if the global
  //    install isn't permitted (e.g. EACCES on a locked-down npm prefix).
  console.error('Playwright not found. Installing it globally (one-time, ~a minute)...');
  try {
    execSync('npm install -g playwright', { stdio: 'inherit' });
    return requirePlaywright();
  } catch (e) {
    console.warn('Global install failed; falling back to a local install in this project.');
    execSync('npm install playwright', { stdio: 'inherit' });
    return require('playwright').chromium;
  }
}

function ensureBrowserInstalled() {
  // Downloads the Chromium binary into the shared per-user cache if it isn't
  // already there. Idempotent and a no-op once installed, so it's cheap on
  // repeat runs (and instant if the lab image pre-installed it).
  try {
    execSync('npx --yes playwright install chromium', { stdio: 'inherit' });
  } catch (e) {
    console.warn('Could not run "playwright install chromium"; continuing in case it is already installed.');
  }
}

function hasFfmpeg() {
  try {
    execSync('ffmpeg -version', { stdio: 'ignore' });
    return true;
  } catch (e) {
    return false;
  }
}

// Returns the duration of a media file in seconds (via ffprobe), or null.
function probeDuration(file) {
  try {
    const out = execSync(
      `ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 "${file}"`,
      { encoding: 'utf8' }
    ).trim();
    const d = parseFloat(out);
    return Number.isFinite(d) ? d : null;
  } catch (e) {
    return null;
  }
}

// --- Background music via Lyria (Vertex AI) ---------------------------------
// Generates an instrumental track from a text prompt using the lyria-002 model,
// then muxes it under the video, matched to the video's length (looped/trimmed
// with a fade in and a fade out at the end so it lands on the final frame).
// Requires ffmpeg and an authenticated gcloud (the lab environment has both).

const LYRIA_MODEL = 'lyria-002';
const LYRIA_REGION = 'us-central1'; // lyria-002 is only served here

function gcloudValue(cmd) {
  return execSync(cmd, { encoding: 'utf8' }).trim();
}

function resolveGcpProject() {
  return (
    process.env.GOOGLE_CLOUD_PROJECT ||
    process.env.GOOGLE_CLOUD_QUOTA_PROJECT ||
    gcloudValue('gcloud config get-value project')
  );
}

// Calls the Lyria predict endpoint and returns WAV audio bytes (Buffer).
async function generateMusic({ prompt, negativePrompt }) {
  const project = resolveGcpProject();
  if (!project) throw new Error('No GCP project (set GOOGLE_CLOUD_PROJECT or run `gcloud config set project`).');
  const token = gcloudValue('gcloud auth print-access-token');
  if (!token) throw new Error('No access token (run `gcloud auth application-default login` / `gcloud auth login`).');

  const url = `https://${LYRIA_REGION}-aiplatform.googleapis.com/v1/projects/${project}/locations/${LYRIA_REGION}/publishers/google/models/${LYRIA_MODEL}:predict`;
  const instance = { prompt };
  if (negativePrompt) instance.negative_prompt = negativePrompt;
  const body = { instances: [instance], parameters: { sample_count: 1 } };

  const res = await fetch(url, {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const text = await res.text().catch(() => '');
    throw new Error(`Lyria API returned ${res.status} ${res.statusText}. ${text.slice(0, 400)}`);
  }
  const json = await res.json();
  const pred = json.predictions && json.predictions[0];
  // Real runtime field is bytesBase64Encoded; audioContent is a doc fallback.
  const b64 = pred && (pred.bytesBase64Encoded || pred.audioContent);
  if (!b64) throw new Error('Lyria response contained no audio bytes.');
  return Buffer.from(b64, 'base64');
}

// Muxes a WAV track under a (silent) video, matched to the video's duration:
// the audio loops to fill long videos, is trimmed to length, and gets a 1s
// fade-in and a 2s fade-out ending exactly on the last frame. Video is copied
// (not re-encoded); audio is encoded to Opus for the .webm container.
function muxMusicIntoVideo({ videoPath, wavPath, outPath, volume }) {
  const dur = probeDuration(videoPath);
  if (!dur) throw new Error('Could not determine video duration for music sync.');
  const fadeIn = Math.min(1.0, dur / 4);
  const fadeOutDur = Math.min(2.0, dur / 3);
  const fadeOutStart = Math.max(0, dur - fadeOutDur);
  const af = `afade=t=in:st=0:d=${fadeIn.toFixed(2)},afade=t=out:st=${fadeOutStart.toFixed(2)}:d=${fadeOutDur.toFixed(2)},volume=${volume}`;
  execSync(
    `ffmpeg -y -i "${videoPath}" -stream_loop -1 -i "${wavPath}" ` +
      `-filter:a "${af}" -map 0:v:0 -map 1:a:0 -t ${dur.toFixed(3)} ` +
      `-c:v copy -c:a libopus -b:a 128k -shortest "${outPath}"`,
    { stdio: 'ignore' }
  );
}

// --- Branding frame ("Gemini World Tour") -----------------------------------
// Loads the CSS + logo assets that get injected into the page so the recording
// carries a branded border and title pill. Returns null if assets are missing.
function loadFrameAssets() {
  const dir = path.join(__dirname, 'assets');
  try {
    return {
      css: fs.readFileSync(path.join(dir, 'overlay.css'), 'utf8'),
      logo: fs.readFileSync(path.join(dir, 'logo.svg'), 'utf8'),
    };
  } catch (e) {
    console.warn('Frame assets not found in ./assets; recording without the branded frame.');
    return null;
  }
}

// Injects the frame into the current page. Idempotent, so it's safe to call
// again after the app re-renders (single-page apps can wipe injected nodes).
async function injectFrame(page, { title, assets }) {
  if (!assets) return;
  try {
    await page.evaluate(({ title, css, logo }) => {
      if (!document.getElementById('gwt-overlay-style')) {
        const style = document.createElement('style');
        style.id = 'gwt-overlay-style';
        style.textContent = css;
        (document.head || document.documentElement).appendChild(style);
      }
      if (!document.getElementById('gwt-frame')) {
        const frame = document.createElement('div');
        frame.id = 'gwt-frame';
        const badge = document.createElement('div');
        badge.id = 'gwt-badge';
        badge.innerHTML = logo; // trusted local SVG asset
        const label = document.createElement('span');
        label.textContent = title; // untrusted-safe: text only
        badge.appendChild(label);
        frame.appendChild(badge);
        document.documentElement.appendChild(frame);
      }
    }, { title, css: assets.css, logo: assets.logo });
  } catch (e) {
    // Non-fatal: a demo without the frame is better than no demo.
  }
}

// --- Simple CLI argument parser ---------------------------------------------
function parseArgs() {
  const args = process.argv.slice(2);
  const options = {
    url: null,                 // resolved below (from --url, --app, or default)
    app: null,                 // ADK dev UI app name
    output: null,              // resolved below
    queries: [],
    typingDelay: 40,           // per-keystroke, natural typing feel
    waitMs: 12000,             // wait for each reply (bump for image/video gen)
    speed: 1.0,                // final playback speed-up (needs ffmpeg if > 1)
    music: null,               // Lyria prompt for background music (opt-in)
    musicNegative: null,       // Lyria negative prompt
    musicVolume: 0.6,          // 0..1 mix level for the music track
    frame: true,               // draw the branded frame
    title: 'Gemini World Tour',
    headless: true,
    viewport: { width: 1280, height: 800 },
    preRollMs: 2500,           // hold on the empty UI before typing
    endPadMs: 2000,            // hold on the final reply before cutting
  };

  for (let i = 0; i < args.length; i++) {
    const arg = args[i];
    if ((arg === '--url' || arg === '-u') && i + 1 < args.length) {
      options.url = args[++i];
    } else if ((arg === '--app' || arg === '-a') && i + 1 < args.length) {
      options.app = args[++i];
    } else if ((arg === '--output' || arg === '-o') && i + 1 < args.length) {
      options.output = path.resolve(args[++i]);
    } else if ((arg === '--query' || arg === '-q') && i + 1 < args.length) {
      options.queries.push(args[++i]);
    } else if (arg === '--delay' && i + 1 < args.length) {
      options.typingDelay = parseInt(args[++i], 10);
    } else if (arg === '--wait' && i + 1 < args.length) {
      options.waitMs = parseInt(args[++i], 10);
    } else if (arg === '--speed' && i + 1 < args.length) {
      options.speed = parseFloat(args[++i]);
    } else if (arg === '--music' && i + 1 < args.length) {
      options.music = args[++i];
    } else if (arg === '--music-negative' && i + 1 < args.length) {
      options.musicNegative = args[++i];
    } else if (arg === '--music-volume' && i + 1 < args.length) {
      options.musicVolume = parseFloat(args[++i]);
    } else if (arg === '--title' && i + 1 < args.length) {
      options.title = args[++i];
    } else if (arg === '--no-frame') {
      options.frame = false;
    } else if (arg === '--headed') {
      options.headless = false;
    } else if (arg === '--help' || arg === '-h') {
      printHelp();
      process.exit(0);
    } else {
      console.error(`Unknown argument: ${arg}`);
      printHelp();
      process.exit(1);
    }
  }

  // Resolve the target URL. Precedence: --url > --app (dev UI) > default frontend.
  if (!options.url) {
    if (options.app) {
      options.url = `http://127.0.0.1:8000/dev-ui/?app=${encodeURIComponent(options.app)}`;
    } else {
      options.url = 'http://localhost:8080/';
    }
  }

  // Default output filename derives from the app name when available.
  if (!options.output) {
    const base = options.app ? `${options.app}_demo` : 'agent_demo';
    options.output = path.join(process.cwd(), `${base}.webm`);
  }

  if (!options.speed || Number.isNaN(options.speed) || options.speed <= 0) {
    options.speed = 1.0;
  }

  if (Number.isNaN(options.musicVolume) || options.musicVolume < 0) {
    options.musicVolume = 0.6;
  }

  // Neutral, domain-agnostic fallback queries. The skill normally passes
  // tailored --query args (from the user's request or their project_brief.md);
  // these only fire if none were provided.
  if (options.queries.length === 0) {
    options.queries = [
      'Hi! What can you help me with?',
      'Can you give me an example of what you can do?',
    ];
  }

  return options;
}

function printHelp() {
  console.log(`
Record a demo video of your agent's chat UI (with a branded frame).

Usage:
  node record-agent.js [options]

Options:
  -q, --query <text>    A message to send. Repeat for a multi-turn demo.
  -u, --url <url>       Full URL of the chat UI to record.
                        Default: http://localhost:8080/ (custom frontend)
  -a, --app <name>      ADK dev UI app name; builds
                        http://127.0.0.1:8000/dev-ui/?app=<name> when --url is unset.
  -o, --output <file>   Output .webm path. Default: ./<app>_demo.webm or ./agent_demo.webm
      --delay <ms>      Per-keystroke typing delay (default 40).
      --wait <ms>       How long to wait for each reply (default 12000).
                        Bump to 30000+ for image/video generation.
      --speed <factor>  Speed up the final video by this factor (default 1.0).
                        e.g. 1.5 trims dead time. Needs ffmpeg; ignored if absent.
      --music <prompt>  Generate instrumental background music with Lyria
                        (lyria-002 on Vertex AI) from this text prompt and mix it
                        under the video, matched to its length. Needs ffmpeg + an
                        authenticated gcloud. e.g. --music "lo-fi chill beats"
      --music-negative <text>  Lyria negative prompt (things to exclude).
      --music-volume <0..1>    Music mix level (default 0.6).
      --title <text>    Frame title text (default "Gemini World Tour").
      --no-frame        Don't draw the branded frame.
      --headed          Show the browser window (default: headless).
  -h, --help            Show this help.
`);
}

(async () => {
  const options = parseArgs();
  const chromium = loadChromium();
  ensureBrowserInstalled();
  const assets = options.frame ? loadFrameAssets() : null;

  console.log('--- Agent UI Recording Tool ---');
  console.log(`Target URL:     ${options.url}`);
  console.log(`Output File:    ${options.output}`);
  console.log(`Queries Count:  ${options.queries.length}`);
  console.log(`Frame:          ${assets ? `on ("${options.title}")` : 'off'}`);
  console.log(`Speed:          ${options.speed}x`);
  console.log(`Music:          ${options.music ? `"${options.music}" (vol ${options.musicVolume})` : 'off'}`);

  // Create a temporary directory for the raw video.
  const tempDir = path.join(process.cwd(), '.video_tmp');
  if (fs.existsSync(tempDir)) {
    fs.rmSync(tempDir, { recursive: true, force: true });
  }
  fs.mkdirSync(tempDir, { recursive: true });

  console.log('\nLaunching Playwright Chromium browser...');
  const browser = await chromium.launch({ headless: options.headless });
  const context = await browser.newContext({
    viewport: options.viewport,
    recordVideo: { dir: tempDir, size: options.viewport },
  });

  const page = await context.newPage();

  console.log(`Navigating to ${options.url}...`);
  try {
    await page.goto(options.url, { waitUntil: 'networkidle', timeout: 30000 });
  } catch (e) {
    console.error(`\nERROR: Could not load ${options.url}.`);
    console.error('Make sure the UI is running (e.g. the frontend on :8080 or the playground on :8000) and reachable.');
    await browser.close();
    process.exit(1);
  }

  // Re-draw the frame whenever the app navigates/re-renders (SPAs wipe nodes).
  page.on('framenavigated', () => injectFrame(page, { title: options.title, assets }));
  await injectFrame(page, { title: options.title, assets });
  await page.waitForTimeout(options.preRollMs);

  // Selector covers the custom frontend (<input id="input">) and the ADK dev UI
  // (<textarea placeholder="Type a message...">), plus generic chat inputs.
  const inputSelector = [
    '#input',
    'textarea[placeholder="Type a message..."]',
    'textarea',
    'input[type="text"]',
    'input:not([type])',
    '[contenteditable="true"]',
  ].join(', ');

  try {
    await page.waitForSelector(inputSelector, { timeout: 15000 });
  } catch (e) {
    console.error('\nERROR: Could not find a chat input on the page.');
    console.error('Check that the URL points at a chat UI, or adjust the selector.');
    await browser.close();
    process.exit(1);
  }
  const chatInput = page.locator(inputSelector).first();

  for (let i = 0; i < options.queries.length; i++) {
    const query = options.queries[i];
    console.log(`\n[Turn ${i + 1}/${options.queries.length}] Typing query: "${query}"`);
    await injectFrame(page, { title: options.title, assets }); // keep frame present
    await chatInput.click();
    await page.waitForTimeout(500);
    await chatInput.pressSequentially(query, { delay: options.typingDelay });
    await page.waitForTimeout(800);
    console.log('Sending message...');
    await chatInput.press('Enter');

    console.log(`Waiting ${options.waitMs / 1000}s for response...`);
    await page.waitForTimeout(options.waitMs);
  }

  // Hold on the final reply so the video doesn't cut off abruptly.
  await page.waitForTimeout(options.endPadMs);

  console.log('\nFinalizing recording...');
  await page.close();
  await context.close();
  await browser.close();

  // Find the saved WebM video.
  const videoFiles = fs.readdirSync(tempDir).filter((f) => f.endsWith('.webm'));
  if (videoFiles.length === 0) {
    console.error('\nERROR: Video recording failed or no webm file generated.');
    process.exit(1);
  }
  const srcPath = path.join(tempDir, videoFiles[0]);
  fs.mkdirSync(path.dirname(options.output), { recursive: true });

  const wantsFfmpeg = options.speed !== 1.0 || !!options.music;
  const ffmpegAvailable = wantsFfmpeg ? hasFfmpeg() : false;
  if (wantsFfmpeg && !ffmpegAvailable) {
    console.warn('ffmpeg not found; skipping speed-up/music. Install ffmpeg to use --speed and --music.');
  }

  // Post-processing pipeline: raw recording -> (optional speed-up) -> (optional
  // music mux) -> output. Each stage writes an intermediate file in tempDir; the
  // last stage writes options.output. Any failure falls back to the prior stage.
  let workVideo = srcPath;

  if (options.speed !== 1.0 && ffmpegAvailable) {
    const spedPath = path.join(tempDir, 'sped.webm');
    console.log(`Speeding video up ${options.speed}x with ffmpeg...`);
    try {
      execSync(
        `ffmpeg -y -i "${workVideo}" -filter:v "setpts=PTS/${options.speed}" -an "${spedPath}"`,
        { stdio: 'ignore' }
      );
      workVideo = spedPath;
    } catch (e) {
      console.warn('ffmpeg speed-up failed; continuing with the original-speed recording.');
    }
  }

  let musicMuxed = false;
  if (options.music && ffmpegAvailable) {
    try {
      console.log(`Generating background music with Lyria (${LYRIA_MODEL})...`);
      const wavBytes = await generateMusic({
        prompt: options.music,
        negativePrompt: options.musicNegative,
      });
      const wavPath = path.join(tempDir, 'music.wav');
      fs.writeFileSync(wavPath, wavBytes);
      console.log('Mixing music under the video (matched to length)...');
      muxMusicIntoVideo({
        videoPath: workVideo,
        wavPath,
        outPath: options.output,
        volume: options.musicVolume,
      });
      musicMuxed = true;
    } catch (e) {
      console.warn(`Music step failed (${e.message}); saving the video without music.`);
    }
  }

  if (!musicMuxed) {
    fs.copyFileSync(workVideo, options.output);
  }

  fs.rmSync(tempDir, { recursive: true, force: true });
  console.log(`\nSUCCESS: Recording saved to ${options.output}`);
})();
