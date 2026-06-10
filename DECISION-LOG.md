# Decision Log

Decisions made during autonomous operation or at ambiguous points during development. See `autonomous-mode.mdc` for the format.

---

<!-- Entries are added below as work progresses. Each entry follows this format:

## [Date] [Short description]
**What I had to decide:** ...
**Options I considered:** ...
**What I chose:** ...
**Why:** ...
**Status:** DECIDED / BLOCKED

-->

## [2026-06-10] CEO Daily Reports email distribution failing since June 3

**What I had to decide:** Why the "CEO Daily Reports" email distribution failed every day since June 3, and how to fix it.

**What I found:** The production database showed every attempt failing with "file not found" for the Ordered and Invoiced report files -- but the files were sitting right there on SharePoint. The app's logs revealed the real error: the Graph API call that looks up the SharePoint *site* was returning 404. The `SP_SITE_URL` setting on the Azure web app pointed to `https://achimonline.sharepoint.com/sites/AchimImportingCoIncTeamSite-D365FO`, a site that does not exist (confirmed by asking Graph directly). The reports actually live on the root site `https://achimonline.sharepoint.com`, under the "D365 F&O" folder in its Documents library. The code swallowed the site-lookup error and reported it as a missing file, which is why the log was misleading. The same wrong-site problem also broke the run_log.csv download the dashboard uses (it had its own hardcoded site name, also wrong) -- which is why Saturday "Shabbos skip" detection failed and the distribution retried in a loop on Saturdays too.

**Options I considered:** (1) Point SP_SITE_URL at the root SharePoint site, matching the local .env that works. (2) Hunt down the "correct" team site URL -- but the file paths all assume the root site's library, so this would need path changes everywhere.

**What I chose:** Option 1: set `SP_SITE_URL=https://achimonline.sharepoint.com` on the Azure web app. Also made two small code fixes: the run_log.csv download now goes through the same shared SharePoint service (instead of its own hardcoded site name), and a dead SP_SITE_URL now raises a clear error naming the setting instead of pretending the file is missing. Added a regression test for that error.

**Why:** Smallest change that restores the working configuration. The local .env already proved the root-site URL resolves every report path correctly.

**Status:** DECIDED
