# Official consumer AI chat history sync paths

Findings date: 2026-11-15

This report covers personal ChatGPT, Claude, Gemini, Grok, Perplexity, and Microsoft Copilot accounts. It reviews developer APIs, official export pages, legal terms, and safe local ingestion options. It does not recommend private web APIs, credential extraction, browser database reads, CAPTCHA bypasses, or other access-control bypasses.

## Result

No official API was found that lists all conversations in a personal consumer account for any of these services. Developer APIs usually expose resources created through the same API account, not history made in a consumer web or app account.

The safe route is to request an official export, save it in a dedicated download folder, and ingest each new file into a local mirror. Human login, account verification, multi-factor authentication, email access, or anti-bot verification can remain necessary.

Google Takeout is the only personal-service export path found that supports a schedule. It can create an archive every two months for one year. The other services require a person to request each export, although some enterprise APIs support continuous organization-level capture.

## Meaning of key terms

Consumer history means chats made under a signed-in personal or eligible consumer account. Developer resources are objects created through a provider API key. Official export means a data copy requested through the provider's documented account page or privacy request process.

The phrase “no official API/path found” means that the reviewed first-party documentation did not publish one. It does not claim that a private endpoint does not exist.

An export schema is the file layout and field layout inside an export. Several providers publish the file type but do not promise a stable schema.

## Comparison

| Service | Official API can list personal account chats? | Official consumer export | Official recurrence | Browser or local database route |
| --- | --- | --- | --- | --- |
| ChatGPT | No official API/path found. The Conversations API needs a known conversation ID. | Privacy Portal or ChatGPT Settings > Data controls > Export data. ZIP with JSON conversations and a local viewer. | On demand. | The export viewer is official. Browser profile databases are unsupported. |
| Claude | No official API/path found. The Messages API receives prior turns from the caller. | Settings > Privacy on the web app or Claude Desktop. | On demand. | No supported browser or app database route. |
| Gemini | No official API/path found. The Interactions API retrieves an interaction by a known ID. | Google Takeout. | On demand, or scheduled every two months for one year. | Takeout includes a local archive browser. Browser profile databases are unsupported. |
| Grok on Grok.com and the mobile app | No official API/path found. The xAI Responses API retrieves a response by a known ID. | Grok app or Grok.com Settings/Data Controls, with a privacy portal fallback. | On demand. | No supported browser or app database route. |
| Grok on X | No official API/path found. | X archive, but inclusion of Grok chats is unconfirmed. | On demand. | No supported browser or app database route. |
| Perplexity | No official API/path found. | Account details > Export my data. | On demand. | No supported browser or app database route. |
| Microsoft Copilot | No personal-account list API was found. The documented Copilot APIs require organization context and licensing. | Microsoft privacy dashboard. Direct CSV download. | On demand. | No supported browser or app database route. |

## ChatGPT and OpenAI

### Official API scope

The [OpenAI Conversations API reference](https://platform.openai.com/docs/api-reference/conversations) documents creating, retrieving, updating, and deleting a conversation by ID. It also documents item operations under a conversation.

Its list method is `GET /conversations/{conversation_id}/items`. The reference calls the method “List all items for a conversation with the given ID.” The path requires `conversation_id`. It does not list conversations or discover conversation IDs.

No documented `GET /conversations` list method was found on 2026-11-15. The API reference also does not connect API conversations to a person's ChatGPT web-account history. Treat API conversations and consumer ChatGPT history as separate stores unless OpenAI publishes a link between them.

### Official export

The current [OpenAI export help page](https://help.openai.com/en/articles/7260999-how-do-i-export-my-chatgpt-history-and-data) documents two routes:

- Use the [OpenAI Privacy Portal](https://privacy.openai.com/) and select a consumer ChatGPT data request.
- Use ChatGPT Settings > Data controls > Export data.

The page gives these download limits:

- “Exports can take up to 7 days to arrive.”
- For a settings export: “The download link expires 24 hours after you receive it.”

A settings export must be downloaded while signed in to the same account. A Privacy Portal export follows the expiry stated in its notification.

The ZIP includes chat history and an `index.html` viewer. The page describes the ZIP contents as:

> “conversations in JSON format, plus other data that may use CSV or other formats.”

The viewer processes files locally and does not upload them.

Settings export is available for ChatGPT Free, Go, Plus, Pro, and eligible ChatGPT Edu workspaces. It is not available for ChatGPT Business, Enterprise, or ChatGPT for Healthcare. Those organizations must use their own managed data access process.

### Safe download-folder use

Save the ZIP in a dedicated folder such as `incoming\chatgpt`. The ingest process must wait until the download has finished and the file size has stopped changing. It must then copy the ZIP to an immutable archive before parsing it.

Keep the ZIP unchanged. OpenAI does not publish a complete field-level schema, so the parser must preserve unknown fields. A changed export layout must fail as an import error instead of causing silent data loss.

### Browser and local database options

OpenAI supplies an official local export viewer. It opens `index.html`, asks the user to choose the extracted folder, and views the exported files locally.

Chrome or Edge profile databases, IndexedDB data, cookies, and cached web requests are not documented mirror interfaces. Their layout can change, and files can be locked or encrypted. Do not use them as the source for a persistent mirror.

### Dated caveats

The export help page was live on 2026-11-15 and showed a recent update. The seven-day preparation period and 24-hour settings-link expiry are current published limits. The JSON file type is documented, but a stable field-level schema was not found. An export cannot restore chats that were already deleted.

[OpenAI's consumer Terms of Use](https://openai.com/policies/terms-of-use/), effective 2026-01-01, prohibit automatic or programmatic extraction and bypassing restrictions. The export page is the safe path for personal history.

## Claude and Anthropic

### Official API scope

The [Anthropic Messages API reference](https://platform.claude.com/docs/en/api/messages) describes `POST /v1/messages`. It says the API supports “single queries or stateless multi-turn conversations.” A caller supplies prior turns in the `messages` parameter. The API does not provide a method to list a person's Claude consumer chats.

The [Claude Compliance API documentation](https://platform.claude.com/docs/en/manage-claude/compliance-api) describes a separate enterprise path. The [setup article](https://support.claude.com/en/articles/13015708-access-the-compliance-api) covers the same path. For Claude Enterprise, the API can provide conversation content, including chats, uploaded files, projects, and app or agent session transcripts. For Claude Platform, it provides Activity Feed events only. The technical documentation says that content endpoints serve Claude Enterprise data only.

This is not a personal Claude history API. It requires eligible organization access. In some cases, it also requires approval from an organization owner or Anthropic sales.

No official API/path was found that lists personal Claude consumer history on 2026-11-15.

### Official export

The current [Claude export help page](https://support.claude.com/en/articles/9450526-how-can-i-export-my-claude-data) documents Settings > Privacy on the web app or Claude Desktop. A mobile app export is not available.

The export includes conversation data, account user data, and voice recordings shared with Anthropic. It does not include the original uploaded files. The page says:

> “Once the export has been processed, you will receive a download link via email.”

The user must be signed in to download it. The link expires 24 hours after creation. The help page says the link “may work only once.”

A Team or Enterprise member can export their own chats after an owner enables that setting. A Primary Owner exports the whole organization through organization settings.

### Safe download-folder use

Save the downloaded file in `incoming\claude`. The ingest process must copy it to an immutable archive before parsing it. The file format and field layout are not documented in the help page, so the parser must detect the format and retain unknown data.

Do not automate the email link or the undocumented request endpoint. A person must start the export, receive the link, sign in, and save the file.

### Browser and local database options

No official Claude export viewer or supported local database interface was found. Claude Desktop caches and browser profile stores are implementation details. Do not read them for the mirror.

### Dated caveats

The export page was live on 2026-11-15 and showed an update during the same week. The 24-hour expiry and original-file exclusion are current published limits. The export schema is undocumented and must be treated as unstable.

[Anthropic's Consumer Terms](https://www.anthropic.com/legal/consumer-terms), effective 2025-10-08, prohibit crawling, scraping, harvesting, unauthorized automated access, and bypassing protections. The official export process is the supported route for personal history.

## Gemini and Google

### Official API scope

The current [Gemini Interactions API guide](https://ai.google.dev/gemini-api/docs/interactions) says that the API became generally available in June 2026. Its resource methods create an interaction. The other methods get, cancel, or delete an interaction by ID.

The [Interactions API reference](https://ai.google.dev/api-reference/interactions-api) does not publish a list-interactions method. A known `Interaction.id` is required for retrieval or deletion. The API also does not document a connection to Gemini Apps account history.

The guide says the API stores Interaction objects by default. Paid tiers retain them for 55 days, and free tiers retain them for 1 day. AI Studio can show stored API interactions for paid projects. These rules do not describe Gemini Apps history or Google Takeout.

No official API/path was found that lists personal Gemini Apps conversations on 2026-11-15.

### Official export

The [Gemini Apps Privacy Hub](https://support.google.com/gemini/answer/13594961) says:

> “You can also export your information”

It links to [Google Takeout](https://takeout.google.com/). The Gemini Privacy Notice was last updated 2026-10-13. The Privacy Hub was last updated 2026-10-26.

The [Takeout help page](https://support.google.com/accounts/answer/3024190?hl=en) documents these current limits and choices:

- Choose a one-time archive or a scheduled export.
- A scheduled export creates an archive every two months for one year.
- The first scheduled archive is created immediately.
- The archive expires in about seven days.
- Each archive can be downloaded five times.
- Google can ask for the password again and can request two-step verification.
- An archive can miss changes made between the request and archive creation.

Takeout can send the archive link by email or place it in Drive, Dropbox, Box, or OneDrive. For a local mirror, the shortest path is the email link followed by a browser download into the dedicated inbox.

### Safe download-folder use

Save each Takeout archive in `incoming\gemini`. The watcher must handle nested product folders and multiple ZIP parts. It must copy every part to the raw archive before extraction.

The cited pages do not document Gemini-specific file names or field layout. The parser must preserve unknown fields. It must record each archive part and its SHA-256 hash.

A scheduled Takeout export can provide a new archive every two months. A person must still download each archive into the folder. The schedule covers one year.

### Browser and local database options

Takeout includes `archive_browser.html`, which documents the archive files and opens them locally. This is an official local view of exported files.

Gemini Apps Activity at `https://myactivity.google.com/product/gemini` is an official view, deletion, and retention control. It is not an export API. Chrome or Edge profile stores are unsupported and must not be read.

### Dated caveats

The Gemini API and Takeout behavior above was checked on 2026-11-15. The API retention periods do not apply to Gemini Apps history. The scheduled export is two-monthly and lasts for one year, not continuously. The Gemini export schema remains undocumented.

## Grok, xAI, and SpaceXSI

SpaceX Super Intelligence LLC (SpaceXSI) operates standalone Grok. Its legal and developer pages use the x.ai domain. This section separates standalone Grok from Grok on X. They have different operators, terms, and export paths.

### Official API scope for standalone Grok

The [xAI Responses API reference](https://docs.x.ai/developers/rest-api-reference/inference/responses) documents `POST /v1/responses`. It also documents `GET /v1/responses/{response_id}` and `DELETE /v1/responses/{response_id}`. The response ID is required for retrieval and deletion. The page says, “New responses will be stored for 30 days and then permanently deleted.”

No list-responses method was found, and the reference does not connect API responses to Grok consumer history. No official API/path was found that lists standalone Grok consumer chats on 2026-11-15.

### Official export for standalone Grok

The [SpaceXSI Consumer FAQ](https://x.ai/legal/faq) says:

> “Please go to your Grok mobile app or Grok.com (Settings/Data Controls) to delete or download your data.”

The FAQ also provides the [SpaceXSI Privacy Portal](https://x.ai/privacy-portal/) as a fallback for a data subject request.

The exact export format, file name, field schema, delivery time, and link expiry are not published. A person must start the request or use the app or site, authenticate, and download the result.

### Safe download-folder use

Save the standalone Grok file in `incoming\grok`. The ingest process must detect the file type and preserve it before parsing. The parser must not assume JSON or any stable field names because the format is undocumented.

Do not send an undocumented export request through code. The privacy portal can require identity verification. Its request contract is not public.

### Browser and local database options

No official Grok export viewer or supported local database interface was found. Grok app caches, browser IndexedDB data, and profile stores are not supported mirror interfaces.

### Dated caveats

[SpaceXSI's Consumer Terms](https://x.ai/legal/terms-of-service) were last updated 2026-10-27. They identify SpaceX Super Intelligence LLC as the operator of the standalone service. They state, “Grok on X. Use of Grok on the X platform is not governed by these Terms.”

### Grok on X

Grok on X falls under the [X Terms of Service](https://x.com/tos), effective 2026-10-09. The [X Privacy Policy](https://x.com/privacy) is effective 2026-01-15.

The official [X archive help page](https://help.x.com/en/managing-your-account/how-to-download-your-x-archive) names this archive request route:

> “Your X data”

The process can require identity verification and an email or push notification. It then provides a ZIP with HTML or JSON files.

The archive documentation lists Direct Messages and other X data. It does not mention Grok conversations. Grok-on-X archive inclusion remains unconfirmed as of 2026-11-15. Do not claim that an X archive contains Grok chats without inspecting an actual archive.

Save the downloaded X archive in `incoming\x`. It is a safe watch target only after the person requests and downloads it through the official flow. X terms require published interfaces. They prohibit scraping without written permission. They also prohibit working around technical limits.

## Perplexity

### Official API scope

No official API/path was found that lists personal Perplexity web or app conversations on 2026-11-15.

The [Perplexity Privacy Notice](https://www.perplexity.ai/hub/legal/privacy-notice), last updated 2026-10-23, limits its scope to consumer services. It does not cover data collected through Perplexity's Enterprise and API offerings when Perplexity acts as a service provider or processor. The developer API is therefore not documented as a consumer history service.

### Official export

The Privacy Notice calls self-service export the recommended option. Its current steps are:

1. Sign in to Perplexity on the website.
2. Open `https://www.perplexity.ai/account/details`.
3. Click “Export my data.”
4. Receive an email with a download link.

The [Self-Serve Data Options page](https://www.perplexity.ai/hub/legal/self-serve-data-options) covers the same account flow. The [Data Request Form](https://perplexity.typeform.com/datarequest) is a fallback for a privacy request.

The export format, field schema, preparation time, and link expiry are not published. A person must sign in, start the export, access the email, and save the file.

### Safe download-folder use

Save the Perplexity download in `incoming\perplexity`. The watcher must copy it to the raw archive before parsing. The parser must detect the format and preserve unknown fields.

Do not automate the Typeform request or an undocumented account endpoint. Identity checks can remain part of the request process.

### Browser and local database options

No official Perplexity export viewer or supported local database interface was found. Local storage from Comet, Perplexity's AI web browser, is not a documented history export. Standard browser profile stores are not documented history exports either. Do not read them for the mirror.

### Dated caveats

The Privacy Notice was last updated 2026-10-23. The export schema and delivery rules were not public on 2026-11-15. The direct self-service page returned HTTP 403 during the final fetch, but the same export steps appear in the live Privacy Notice.

## Microsoft Copilot

### Official API scope

The [Microsoft Privacy Statement](https://privacy.microsoft.com/privacystatement), last updated November 2026, describes personal Copilot export. A signed-in user can “view, access, export and delete Copilot activity history” from the Microsoft privacy dashboard. The statement does not publish a personal-account API that lists all Copilot conversations.

The [Microsoft 365 Copilot APIs overview](https://learn.microsoft.com/en-us/microsoft-365/copilot/extensibility/copilot-apis-overview) documents enterprise APIs for retrieval, search, chat, and interaction export. It also documents change notifications. The Interaction Export API can capture and archive Copilot interactions for compliance. Change notifications can report new interactions.

These APIs require Microsoft 365 organization context, authentication, and Microsoft 365 Copilot licensing. The overview requires a Microsoft 365 Copilot license for each user and an E3, E5, or equivalent subscription. They are not the documented route for a personal Copilot account dashboard export.

No official personal-account list API was found on 2026-11-15.

### Official export

The current [Microsoft Copilot privacy dashboard guide](https://support.microsoft.com/en-us/privacy/manage-your-copilot-activity-history-in-the-privacy-dashboard) covers personal Microsoft accounts. It defines activity history as a record of what a person types in Copilot and the AI-assisted responses received from Copilot.

The route is:

1. Sign in to `https://account.microsoft.com/privacy`.
2. Open Privacy > Empower your productivity > Copilot > Your Copilot app activity history > Copilot apps.
3. Select “Export all activity history.”
4. Save the downloaded CSV file.

Separate export choices exist for Copilot in Microsoft 365 apps and Chat in the Microsoft Copilot app. The [work or school activity-history page](https://support.microsoft.com/en-us/privacy/delete-your-microsoft-365-copilot-activity-history) documents deletion, not export. Use the enterprise Copilot APIs for organization-level capture.

### Safe download-folder use

Save the CSV in `incoming\microsoft`. The ingest process must copy it to the raw archive before parsing. The help page does not define the CSV columns. The parser must preserve unknown columns and record the source file hash.

The export is a direct browser download. There is no documented personal-account schedule or export API. A person must sign in and select the export each time.

### Browser and local database options

No official Copilot local viewer or supported browser or app database interface was found. Edge profile stores and Microsoft app caches are unsupported and must not be read.

### Dated caveats

The Privacy Statement was last updated November 2026. The [Microsoft Services Agreement](https://www.microsoft.com/en-us/servicesagreement) was effective 2026-09-30. It allows account data access through the privacy dashboard while prohibiting access-control circumvention and impermissible scraping.

## Safe local options for all services

Browser profile databases and app-local databases are not supported mirror paths for any service in this report. They can contain unrelated personal data, credentials, session state, and provider records. Their schemas can change without notice. The files can be locked or encrypted while an app is running.

The safe local options are narrow:

- OpenAI supplies a local viewer inside the ChatGPT export.
- Google supplies `archive_browser.html` inside a Takeout archive.
- Microsoft supplies a direct CSV download.
- Claude, Grok, Perplexity, and X supply downloadable files without a documented local viewer for this mirror.

A download folder is safe because the person obtained the file through an official export. Watching the folder does not make a private request endpoint official.

## Shortest safe Windows design

Use one local root and keep the raw export as the source of truth:

```text
C:\AI-Chat-Mirror\
  incoming\
    chatgpt\
    claude\
    gemini\
    grok\
    perplexity\
    microsoft\
    x\
  raw\
    chatgpt\
    claude\
    gemini\
    grok\
    perplexity\
    microsoft\
    x\
  work\
  index\
    mirror.sqlite
  logs\
```

Use this flow:

1. A person requests an export through the official page and saves it in the matching `incoming` folder.
2. A small poller checks the folders every minute. Polling needs no new package and is enough for this low-volume use.
3. The poller ignores temporary download names such as `.crdownload` and waits until the file size is unchanged across two checks.
4. The poller copies the finished file to `raw\<provider>\<UTC timestamp>-<sha256>.<extension>`. It uses create-new behavior. It never overwrites an older file. After it verifies the copy and SHA-256 hash, it removes the incoming file to prevent duplicate imports.
5. The poller extracts the copy into a new `work\<sha256>` folder. It never extracts in place.
6. The parser writes normalized records to `index\mirror.sqlite`. It appends an import record and a source-file record for every file.
7. A later or changed export adds new source and version records. It does not delete the earlier raw file or version.
8. The poller records errors and leaves the raw file in place. An operator can fix the parser and run it again.
9. The operator can rebuild `mirror.sqlite` from the raw archives at any time. The raw archive is the append-only mirror. SQLite is a rebuildable search index.

Each normalized record stores the provider, role, content, and source file hash. It also stores a source conversation ID, a source message ID, and timestamps when the export provides them. Use a content hash when the export has no stable message ID.

Keep the mirror local. Use Windows access controls to limit the folder to the user's account. Put it on a BitLocker-protected volume when available. BitLocker is Windows volume encryption. The files can contain passwords, personal data, private source code, and health or financial details. Do not upload them to a hosted parser.

Do not put account passwords, session cookies, export tokens, or identity-verification values in the watcher. The watcher needs only folder and file access.

## Human steps that remain

| Service | Human action | Current wait or identity step |
| --- | --- | --- |
| ChatGPT | Request through Privacy Portal or Settings > Data controls, then download. | Up to seven days. Settings links expire after 24 hours. Account email or phone access can be required. |
| Claude | Use Settings > Privacy on the web app or Desktop, then download. | Signed-in email link. The link expires after 24 hours and “may work only once.” |
| Gemini | Create or schedule a Takeout export, then download it. | Google can require a password or two-step verification. Each archive expires after about seven days and allows five downloads. |
| Grok | Use Grok app or Grok.com Settings/Data Controls, or submit a privacy request. | The export can require account login and identity checks. Delivery timing is undocumented. |
| Grok on X | Request an X archive through “Your X data,” then inspect the archive for Grok chats. | Identity verification plus email or push notice. Grok inclusion is unconfirmed. |
| Perplexity | Use Account details > Export my data, then download from email. | Signed-in account and email access. Delivery timing is undocumented. |
| Microsoft Copilot | Use the Microsoft privacy dashboard and select the CSV export. | Signed-in Microsoft account. |

A folder watcher cannot remove these human steps unless the provider publishes a supported export API or schedule. Continuous consumer mirroring is not fully available through the documented personal-service paths reviewed on 2026-11-15.

## Legal and safety boundaries

The reviewed terms support the export-first design and warn against automatic extraction from the web services:

- [OpenAI Terms of Use](https://openai.com/policies/terms-of-use/), effective 2026-01-01, prohibit automatic or programmatic extraction and bypassing restrictions.
- [Anthropic Consumer Terms](https://www.anthropic.com/legal/consumer-terms), effective 2025-10-08, prohibit crawling, scraping, harvesting, unauthorized automated access, and bypassing protections.
- [SpaceXSI Consumer Terms](https://x.ai/legal/terms-of-service), last updated 2026-10-27, govern standalone Grok and route Grok on X to the X terms.
- [X Terms of Service](https://x.com/tos), effective 2026-10-09, require published interfaces and prohibit scraping without written permission and working around technical limits.
- [Microsoft Services Agreement](https://www.microsoft.com/en-us/servicesagreement), effective 2026-09-30, permits privacy-dashboard export and prohibits circumvention and impermissible scraping.

This report does not cover private web endpoints, copied browser requests, or session-cookie extraction. It also does not cover local browser database scraping, app-database scraping, CAPTCHA or anti-bot bypasses, or credential extraction. These paths are undocumented. They can expose unrelated data. They also conflict with one or more provider terms.

## Verification note

The review checked official pages against first-party documentation on 2026-11-15. The X archive help page and Perplexity self-service page returned HTTP 403 during the final direct fetch. Earlier research retrieved the X details from that official page. The live Perplexity Privacy Notice also contained the export steps. No connected desktop browser was available for a final visual review of either page.

Several export schemas remain undocumented. The mirror must keep every raw file so that a later parser can reprocess it without asking the provider for an export again.
