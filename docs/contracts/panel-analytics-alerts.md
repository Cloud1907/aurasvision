# Panel analytics and alert rules

User-authorized scope: replace camera-dominated panel with real analytical data,
today by default and last seven days; camera/analysis coverage; configurable
camera-specific alarm popup and sound. Existing live playback and event filters remain.

Visual selection: awaiting user's choice among latest three supplied images.
No visual implementation before selection. Backend work is independent.

Acceptance:
- Aggregate alarm counts over the selected local-time range without feed limits.
- Show all-time pending separately; distinguish cameras from test video sources.
- Derive enabled analyses from actual camera tasks, separate from recent health.
- Persist camera/type/popup/sound/cooldown rules; reject invalid configurations.
- Initial connection does not replay old alarms; new alarms are consumed once.
- Muting audio does not acknowledge an alarm. Acknowledgement uses existing API.
- Browsers require explicit interaction to activate sound; surface unavailable audio.
- No simulated events or fixed statistics in the production panel.

Verification: backend aggregation/storage tests, notification policy tests,
frontend build, browser interactions and desktop/mobile screenshots.
