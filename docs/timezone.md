# Timezone Cog Documentation
Set or view timezones for users.
Command group name: `timezone`

## Storage
Timezones are stored in a SQLite database at `data/timezones.db`, in a table called `user_timezones`. Each row holds a user id and their saved timezone string. The table is created automatically when the cog loads, if it does not already exist.
Saving a timezone for a user who already has one set will overwrite the old value.

## Autocomplete
The `timezone` parameter on the `at` and `set` commands uses autocomplete. It searches all available IANA timezone names using Python's `zoneinfo` library, matching against what the user has typed so far, and returns up to 25 matches. Underscores in timezone names are shown as spaces in the suggestion list.

## /timezone for
View a user's timezone, defaulting to your own.

**Parameters**

| Name | Type | Required | Description |
|------|------|----------|--------------|
| user | user | no | The user whose timezone you want to view. Defaults to yourself. |

**Behavior**
If the target user is the app/bot itself, the command replies with a random time related quote (easteregg) instead of a timezone. Usually, across other cogs, the ErrorUI class is used here.

If the target user is another bot/app, the command replies with an errorUI saying you tried to view a bot's timezone.

If the target user has no timezone saved, the command replies with an errorUI stating that they do not have a timezone set. The wording changes depending on whether the target is yourself or someone else.

If you are viewing your own timezone, the command replies with the current time and date in **your** saved timezone.

If you are viewing someone else's timezone and you don't have your own timezone saved, the command replies with their current time only, and a note asking you to set your own timezone to see time difference.

If both you and the target user have timezones saved, the command replies with the target user's current time, the time difference between your timezone and theirs in hours, and whether you are ahead or behind them, and your own current time. If the two of you are in the same timezone, the command instead states that you share the same timezone. If your dates differ, the reply also states both dates.

**Example**
Running `/timezone for user:@saltgranule` when Alice is in a timezone 3 hours ahead of you might reply:
`It is currently 5:00 PM for @saltgranule. You are 3 hours behind, at 2:00 PM. You are both on the same day.`

## /timezone at
View the current time in a given timezone or region.

**Parameters**

| Name | Type | Required | Description |
|------|------|----------|--------------|
| timezone | string | yes | The name or region of the timezone to view. Supports autocomplete. |

**Behavior**
If the given timezone is valid, the command replies with the current time and date for that timezone.
If the given timezone is not valid, the command replies with an error stating that it is not a valid timezone.

**Example**
Input: `Europe/London`
Output: `It is currently 3:00 PM for those in Europe/London. It is August 22nd, 2026 for them.`

## /timezone set
Set your own timezone.

**Parameters**

| Name | Type | Required | Description |
|------|------|----------|--------------|
| timezone | string | yes | The timezone to save for your account. Supports autocomplete. |

**Behavior**
If the given timezone is valid, it is saved to the database under your user id, replacing any previously saved timezone. The command replies confirming the timezone was set.
If the given timezone is not valid, the command replies with an error stating that it is not a valid timezone. Nothing is saved.

## /timezone reset
Reset your saved timezone.

**Parameters**
None.

**Behavior**
If you have a timezone saved, it is deleted from the database, and the command replies confirming the reset.
If you do not have a timezone saved, the command replies with an error stating that you do not have a timezone set.