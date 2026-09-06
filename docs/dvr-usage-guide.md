# DVR Usage Guide

HDHR Open supports a flexible, dual-engine DVR architecture allowing you to record live broadcast television either through HDHR Open's **Built-in DVR** or through SiliconDust's **Official HDHomeRun DVR Service**.

---

## Dual-Engine DVR Architecture

HDHR Open integrates two distinct recording backends:

1. **HDHomeRun Open Built-in DVR (Self-Hosted)**:
   - Records directly to your local server storage.
   - Supports title matching, custom start/end padding, episode retention limits, and keyword/regex rules.
   - Does **not** require an active SiliconDust DVR subscription.
   - Can record any program or time slot from any guide source (XMLTV, Schedules Direct, or HDHomeRun Cloud).

2. **HDHomeRun Official DVR (SiliconDust Service)**:
   - Coordinated via SiliconDust's cloud API (`api.hdhomerun.com`) and recorded by your local HDHomeRun record engine device or NAS.
   - Requires an active HDHomeRun DVR subscription.
   - Relies on SiliconDust's proprietary cloud catalog to track airings and deduplicate episodes across broadcasts.

---

## Guide Sources & Series ID Requirements

SiliconDust's cloud DVR engine strictly requires a proprietary SiliconDust **Series ID** (e.g., `SH012345670000`, `EP...`, or `MV...`) for every recording rule created. Without a Series ID, SiliconDust's cloud API rejects rule creation with `HTTP 400 Bad Request`.

Depending on your configured guide provider priority (e.g. XMLTV vs. HDHomeRun Cloud):

- **HDHomeRun Cloud Guide**: Provides native SiliconDust `SeriesID` identifiers for all airings, but is typically limited to a ~2.5-day rolling window.
- **XMLTV Feeds**: Provide extended scheduling (often 7 to 14 days) and custom channel lineups, but standard XMLTV XML feeds do not contain SiliconDust `SeriesID` identifiers.
- **Schedules Direct**: Provides Gracenote program IDs (`TMS ID`).

---

## Cross-Provider Metadata Enrichment

To provide the best of both worlds, HDHR Open features an automatic **Cross-Provider Metadata Enrichment** pipeline:

1. When multiple guide sources are configured (for example, XMLTV for extended schedules alongside HDHomeRun Cloud), HDHR Open cross-references airings.
2. If an XMLTV airing lacks an external program ID, the system checks for a corresponding broadcast in HDHomeRun Cloud on the same channel within a 60-second window and matching normalized title.
3. If a match is found, HDHR Open safely enriches the XMLTV airing with:
   - SiliconDust `SeriesID` (`external_program_id`)
   - High-resolution poster/artwork (`image_url`)
   - Program synopsis / description
   - Season and episode numbering
4. This enables scheduling with the Official HDHomeRun DVR directly from XMLTV guide listings without manual intervention.

---

## Automatic Fallback to Built-in DVR

When a program cannot be matched to a SiliconDust Series ID (for example, airings beyond HDHomeRun Cloud's ~2.5-day window, local community programming, or guide feed mismatches), HDHR Open ensures your recording is never lost:

### 1. Smart UI Defaults
- When opening the **Recording Options Dialog** for an airing without a Series ID, the server selection automatically defaults to **HDHomeRun Open Built-in DVR**.
- If you select the HDHomeRun DVR server for an airing lacking a Series ID, an informational hint appears:
  > *"HDHomeRun DVR requires a SiliconDust Series ID. If no match is found, this recording will automatically use the Built-in DVR."*

### 2. User Confirmation Dialog & "Don't ask again"
- When you attempt to schedule an airing that lies beyond the HDHomeRun guide window or lacks a SiliconDust Series ID while the Official HDHomeRun DVR is active (via the **Recording Options Dialog** or quick actions in the **Guide Grid**):
  - A confirmation dialog appears:
    > *"Schedule on Built-in DVR? '[Program Title]' is beyond the HDHomeRun guide window or lacks a SiliconDust Series ID. It will be scheduled using the Built-in DVR instead."*
  - The dialog includes a **"Don't ask again"** checkbox. Checking this stores your preference in your browser's local storage (`localStorage`), allowing future fallbacks to schedule seamlessly on the Built-in DVR without interrupting you.

### 3. Backend Fallback & Error Recovery
- When a recording request targets the HDHomeRun DVR:
  1. The backend first inspects the guide program cache to resolve a matching SiliconDust Series ID.
  2. If no Series ID exists, or if SiliconDust's cloud API rejects the rule (e.g., due to an unrecognized program or HTTP 400), the backend automatically falls back to creating the rule on the **Built-in DVR**.
  3. The reason for fallback is permanently recorded with the rule (e.g. `"Airing lacks a SiliconDust Series ID in the guide; fell back to Built-in DVR."`).

### 4. User Notifications & Badging
- **Notification Banner**: Upon creating a rule that triggered fallback, an informational alert banner is displayed:
  > *"Scheduled on Built-in DVR: '[Program Title]' lacks a SiliconDust Series ID for HDHomeRun DVR."*
- **Rule Badge**: In the **Scheduled Recordings** view, the rule is clearly tagged with a `Built-in (Fallback)` badge. Hovering or inspecting the rule displays the exact fallback reason.

---

## Managing Scheduled Rules & Safe Cancellation

- **Server Filter Bar**: In the Recordings page (`/recordings`), use the server filter chips (**All Servers**, **Built-in DVR**, **HDHomeRun DVR**) to inspect rules and captures per engine.
- **Editing Rules**: You can modify start padding, end padding, retention counts, and channel targets for any rule at any time using the ⚙️ **Recording Options** button.
- **Safe Cancellation with Confirmation**:
  - To prevent accidental deletion of series rules when you simply intended to close the dialog or discard unsaved changes, the cancellation action is explicitly labeled **"Cancel Recording"** in red and separated from the dialog's **"Close"** and **"Update Recording"** buttons.
  - Clicking **"Cancel Recording"** (from the Recording Options dialog, the guide grid context menu, or the scheduled recordings list) opens a confirmation modal:
    > *"Cancel Recording Rule? Are you sure you want to cancel the recording rule for '[Program Title]'? Upcoming airings will not be recorded."*
  - You can safely choose **[Keep Recording]** to dismiss or **[Cancel Recording]** to confirm deletion.
