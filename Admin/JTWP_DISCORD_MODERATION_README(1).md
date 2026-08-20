# 🛡️ JTWP Discord Moderation System

The **JTWP Discord Moderation System** is part of the Pavlov Data
Collector project. It provides a structured workflow for player reports,
formal warnings, ban cases, staff review, voting, punishment decisions,
ban expiration, and permanent moderation records.

The system is designed so that a report or accusation does **not
automatically become a punishment**. Cases are documented, reviewed,
classified against the JTWP rules, and---when a ban is proposed---sent
through staff voting and final Senior Admin review.

------------------------------------------------------------------------

## 🎯 Purpose

The moderation system is intended to help JTWP staff:

-   📣 Receive structured player reports.
-   ⚠️ Issue and permanently record formal warnings.
-   🔨 Build documented ban cases.
-   📚 Reference a consistent rules and punishment policy.
-   🗳️ Allow administrators to review and vote on serious cases.
-   🛡️ Require Senior Admin approval before a proposed ban is applied.
-   ⏳ Track temporary bans and automatically lift them when they
    expire.
-   📨 Notify affected players when a ban begins and when a temporary
    ban ends.
-   📂 Maintain permanent moderation history for players.
-   🔎 Preserve an audit trail of important moderation actions.
-   🚩 Identify situations that are not adequately covered by the
    existing rules.

------------------------------------------------------------------------

# 🤖 Main Moderation Commands

## 📣 `!reportPlayer`

**Who can use it:** 🌐 Anyone

`!reportPlayer` is the community reporting command. It allows a player
to privately report another player or an incident to the moderation
team.

After the command is triggered, the bot moves the report into a
**private DM questionnaire**. The reporter provides information such as
the target player, server, incident description, and available evidence.

A community reporter is **not responsible for deciding which JTWP rule
was violated**. Reports initially remain unclassified so that an
administrator can review the information and determine the appropriate
rule/category.

### Typical use

Use `!reportPlayer` for situations such as:

-   🚨 Suspected rule violations
-   🤬 Harassment, bullying, threats, or hate speech
-   🎯 Intentional team killing
-   🕵️ Suspected cheating or unfair software
-   🔐 Disclosure of another player's private information
-   💥 Attempts to interfere with server performance
-   📢 Spam or disruptive behavior
-   👮 Problems involving staff behavior or abuse of privileges

Submitting a report does **not** mean the reported player is
automatically guilty or punished.

------------------------------------------------------------------------

## ⚠️ `!warning`

**Who can use it:** 👮 Admin / 👑 Owner

`!warning` creates a **formal moderation warning** against a player.

The administrator completes the case through DMs and selects the most
appropriate rule category and rule from the JTWP rules database.

The warning becomes part of the player's permanent moderation history
and can provide context if the player is involved in future incidents.

A warning is appropriate when staff determine that behavior requires
formal documentation but does not currently justify a ban.

If the situation does not fit an existing rule, the administrator can
mark the case as having **no matching rule**. The warning remains valid
and the rules gap can be reviewed later.

------------------------------------------------------------------------

## 🔨 `!banLog`

**Who can use it:** 👮 Admin / 👑 Owner

`!banLog` creates a **proposed ban case**.

⚠️ **Running `!banLog` does not immediately ban the player.**

The command starts a private case-building process. The administrator
records the player, server, incident, evidence, rule/category, and other
relevant information.

Once completed, the case is permanently saved and posted to the private
administration channel for staff review.

The case then enters the voting and Senior Admin review process.

------------------------------------------------------------------------

# 🔄 How a Moderation Case Plays Out

A serious case follows a structured path:

``` text
📣 Report / ⚠️ Warning / 🔨 Ban Case
                  ↓
          📨 Private DM Form
                  ↓
          📂 Case Is Saved
                  ↓
        📚 Rule Classification
                  ↓
      🛡️ Admin Review Channel
                  ↓
             🗳️ Voting
                  ↓
       👑 Senior Admin Review
                  ↓
        ⚖️ Final Determination
          ↙       ↓        ↘
      Reject   Temp Ban   Permanent Ban
                  ↓
           ⏳ Ban Timer
                  ↓
           🔓 Automatic Unban
                  ↓
        📂 Permanent History
```

### 1. 📨 Information Collection

The bot collects the information required to build the case through DMs.
This keeps the case-building conversation separate from public channels.

### 2. 📂 Permanent Case Record

The case receives a unique Case ID and is written to the moderation
data.

Important actions are also recorded in the moderation audit history and
the affected player's moderation history.

### 3. 📚 Rule Classification

Warnings and proposed bans require the administrator to select the
closest rule/category.

Player-submitted reports begin unclassified and can be classified by an
administrator during review.

### 4. 🚩 No Matching Rule

Not every possible incident can be predicted in advance.

If no existing rule adequately covers the situation, staff may mark the
case as having no matching rule. This **does not automatically
invalidate the case**.

Instead, the case is flagged as a rules gap so the moderation policy can
later be expanded.

### 5. 🛡️ Administration Channel

The completed case is posted as a readable Discord embed in the private
moderation channel.

The case can include:

-   👤 Player information
-   🖥️ Server
-   📝 Incident summary
-   📚 Rule/category
-   🔎 Evidence
-   📊 Previous moderation history
-   ⚖️ Rule punishment guidance
-   🗳️ Current staff votes
-   📌 Current case status

### 6. 🗳️ Staff Voting

Administrators can review the case and vote using reactions:

-   👍 **Approve**
-   👎 **Reject**
-   ⚠️ **Escalate**

Voting provides staff input, but the vote itself does **not
automatically execute a ban**.

### 7. 👑 Senior Admin Review

A proposed ban remains pending until a **Senior Admin or Owner** makes
the final decision.

Senior staff can choose to:

-   ⏳ Apply a temporary ban
-   🔨 Apply a permanent ban
-   ❌ Reject/close the case

For a temporary ban, the Senior Admin selects the number of days.

------------------------------------------------------------------------

# ⏳ Temporary Bans

A Senior Admin or Owner can approve a temporary ban with:

``` text
!caseTempBan <CASE-ID> <days>
```

When approved, the system:

1.  🔨 Issues the Pavlov RCON ban.
2.  🕐 Records the exact UTC start time.
3.  ⏳ Calculates the expiration time from the number of days selected.
4.  📂 Adds the ban to the active-ban database.
5.  📝 Adds the action to the player's permanent moderation history.
6.  📨 Attempts to DM the banned player with the case and duration.
7.  📢 Posts the ban action to administration.

The bot periodically checks active temporary bans. When the expiration
time is reached, it attempts to issue the RCON unban automatically.

After a successful scheduled unban, the system records the event
permanently, removes the ban from the active-ban list, notifies
administration, and attempts to DM the player that the ban has been
lifted.

------------------------------------------------------------------------

# 🔨 Permanent Bans

A Senior Admin or Owner can approve a permanent ban with:

``` text
!casePermBan <CASE-ID>
```

A permanent ban has no scheduled expiration and remains part of the
player's permanent moderation record.

------------------------------------------------------------------------

# ❌ Rejecting a Ban Case

Senior staff can close a proposed ban without applying it:

``` text
!caseReject <CASE-ID> <reason>
```

The rejection and reason are retained in the case history so there is
still a record of the review and final decision.

------------------------------------------------------------------------

# 📚 Rules & Punishment Reference

The moderation system uses:

``` text
resource/rules_and_punishments.json
```

This file acts as the bot's structured moderation-policy reference.

The rules currently cover areas including:

-   🚫 Racism
-   🚫 Sexist behavior
-   🤝 Respect for other players
-   🚫 Bullying and harassment
-   🎯 Intentional team killing
-   🖥️ Intentional server-performance disruption
-   🔐 Disclosure of private information
-   🕵️ Cheating or software used for an unfair advantage
-   🔞 Gore or sexually explicit material
-   🎮 Manipulation of a game mode for an unfair advantage
-   ⚠️ Threatening other players
-   🎭 Deliberately preventing others from enjoying the server
-   📢 Spam and intentionally annoying behavior
-   🚫 Slurs and other hate speech
-   🎭 Impersonation
-   👮 Following legitimate staff instructions
-   ⚖️ Staff being held to the rules as well
-   📣 Reporting problems instead of escalating them
-   🛑 Abuse of admin or staff privileges

The JSON contains more than rule titles. It is intended to provide
structured information that can help staff understand the rule, classify
the behavior, review evidence, and consider an appropriate punishment.

Punishment information is **guidance for staff**, not an automatic
sentencing system. Context, evidence, severity, previous history,
aggravating factors, and mitigating factors can all matter when a case
is reviewed.

------------------------------------------------------------------------

# 🧭 Additional Case Commands

### 📚 `!caseClassify`

``` text
!caseClassify <CASE-ID> "<Category>" [RuleID|none] [reason]
```

Allows an Admin or Owner to classify or update a case.

This is especially useful for `!reportPlayer` cases, because community
reports begin without the reporter choosing the rule.

### 🔎 `!caseInfo`

``` text
!caseInfo <CASE-ID>
```

Allows an Admin or Owner to display the current information for a
moderation case.

### ⏳ `!caseTempBan`

``` text
!caseTempBan <CASE-ID> <days>
```

Senior Admin / Owner only. Approves and starts a temporary ban.

### 🔨 `!casePermBan`

``` text
!casePermBan <CASE-ID>
```

Senior Admin / Owner only. Approves a permanent ban.

### ❌ `!caseReject`

``` text
!caseReject <CASE-ID> <reason>
```

Senior Admin / Owner only. Rejects and closes the case.

------------------------------------------------------------------------

# 📂 Permanent Moderation Records

Global moderation information is stored under:

``` text
/home/steam/jtwp-collector-data/global/moderation/
├── cases/
├── active_bans.json
├── offenders.json
├── reports.jsonl
├── warnings.jsonl
├── bans.jsonl
└── audit.jsonl
```

Player-specific moderation history is stored under:

``` text
/home/steam/jtwp-collector-data/players/records/{product_id}/moderation/
├── reports.jsonl
├── warnings.jsonl
├── bans.jsonl
└── history.jsonl
```

Historical moderation information is retained after a temporary ban
expires. Removing an active ban does not erase the history of the case.

------------------------------------------------------------------------

# 🔐 Permission Summary

  -----------------------------------------------------------------------
  Command                 Who Can Use It          Purpose
  ----------------------- ----------------------- -----------------------
  📣 `!reportPlayer`      🌐 Anyone               Submit a player report

  ⚠️ `!warning`           👮 Admin / 👑 Owner     Create a formal warning

  🔨 `!banLog`            👮 Admin / 👑 Owner     Build a proposed ban
                                                  case

  📚 `!caseClassify`      👮 Admin / 👑 Owner     Classify a case against
                                                  the rules

  🔎 `!caseInfo`          👮 Admin / 👑 Owner     Review a case

  ⏳ `!caseTempBan`       🛡️ Senior Admin / 👑    Approve a temporary ban
                          Owner                   

  🔨 `!casePermBan`       🛡️ Senior Admin / 👑    Approve a permanent ban
                          Owner                   

  ❌ `!caseReject`        🛡️ Senior Admin / 👑    Reject and close a case
                          Owner                   
  -----------------------------------------------------------------------

------------------------------------------------------------------------

# 🛡️ Moderation Philosophy

The system is built around **documentation, consistency, accountability,
and human review**.

A report is information---not an automatic conviction. A rule reference
provides guidance---not an automatic punishment. Serious enforcement
actions remain subject to staff review, and proposed bans require final
authorization from trusted senior staff.

The goal is to give JTWP administrators the information and tools needed
to make better-informed moderation decisions while maintaining a
permanent and reviewable history of important actions.

**📊 Better records. ⚖️ Better decisions. 🛡️ Stronger communities.**
