# AI Cog Documentation
AI query tools powered by google's gemini API, with optional DDGS web search grounding.
Command group name: `ai`

## ask command
Path: `/ai ask`

Ask a free AI model a question, with an optional web search for grounding.

**Parameters**

| Name | Type | Required | Description |
|------|------|----------|--------------|
| prompt | string | yes | The question or prompt to send to the AI model. |
| search | boolean | no | Whether to ground the response with web search context. Defaults to false. |

**Rate limit**
Limited to 2 uses per 60 seconds, per the command's cooldown. Expect this to change as Melvin grows to a larger, more demanding audience.

**Behavior**
The command defers its response, since generation can take a few seconds.

If `search` is true, the prompt is first run through a DuckDuckGo web search (via DDGS), pulling up to 5 results. Each result's title, URL, and snippet are formatted into a block of search context. This context is passed to Gemini alongside the prompt, and the model is instructed to ground its answer using that context relative to the current date. This pretty much allows the AI model to reach information outside of it's context window.

If `search` is false, the prompt is sent to Gemini as is, with no search context attached.

In both cases, the system prompt tells Gemini the current date, and asks it to keep responses short and tidy to fit Discord's 4000 character limit, to write in brief paragraphs rather than tables or graphs, and to avoid emojis unless asked for because emoji's look weird.

The model used is `gemini-3.1-flash-lite`, with temperature set to 0.7.

Once a response comes back, it is truncated to 1500 characters if needed. The final reply is built as a Discord CV2 message, containing:
- A section showing the original prompt (escaped for markdown), with a link button to [Google AI Studio](https://aistudio.google.com/).
- A separator.
- The AI response text, followed by a small note showing how long the request took, and whether the response was grounded with DDGS web search.

**Error handling**
If Gemini returns an empty response, or if the API call fails for any reason, the command replies with an errorUI class message.

If the command is used more than twice within 60 seconds, the command replies with a rate limit message instead of running.

Any other unexpected error during the command is logged, and the user is shown a generic error message with the exception.