# Deploying

- Never deploy (`agents-cli deploy`, `gcloud run deploy`, or similar) unless the user explicitly asks for it in their current message.
- After a code change, test locally with `agents-cli run` or the local Playground. Don't redeploy just to test.
- If a change only takes effect on the deployed agent, say so and ask before deploying.
