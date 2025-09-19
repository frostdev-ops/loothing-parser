A Developer's Guide to Parsing the World of Warcraft Advanced Combat Log
Introduction
The World of Warcraft combat log is a powerful, high-fidelity data source that records every action and consequence within a combat scenario. For developers, it represents an opportunity to build sophisticated performance analysis tools that can deconstruct encounters, evaluate player decisions, and provide actionable feedback. The log is generated as a simple, append-only text file, WoWCombatLog.txt. Its true value, however, lies in the granularity and density of the events it captures when properly configured.   

The fundamental architectural challenge in parsing this data lies in its nature as a raw, stateless stream of chronological events. The log file itself holds no memory; it does not know if a buff applied 100 lines ago is still active. Therefore, the primary task of a combat log parser is to transform this unstructured text stream into a structured, queryable dataset. This is achieved by building a sophisticated state machine—an internal model of the game's combat state that is meticulously updated with each event processed. This guide serves not merely as a file format specification, but as an architectural blueprint for constructing a robust analysis engine capable of reconstructing the complex dynamics of World of Warcraft combat.

Section 1: Foundations of Combat Logging
Before writing a single line of parsing code, a developer must understand the prerequisites for generating valid and complete data. The integrity of any subsequent analysis hinges on the correct in-game configuration and management of the log file itself.

1.1. Enabling Advanced Combat Logging: The Prerequisite for Data Integrity
The cornerstone of any modern combat log parser is a feature called "Advanced Combat Logging." This is a mandatory, non-default setting located within the game client's System > Network options menu. Enabling this feature expands the log's output to include a wealth of additional parameters essential for deep analysis. These include globally unique identifiers (GUIDs) for all participants, resource states (health, mana, rage, etc.) after each event, and detailed information about auras (buffs and debuffs). Without this setting, the log lacks the necessary detail to build a comprehensive state model, rendering a parser unable to perform its core functions.   

The richness of this data, however, is entirely dependent on user action. Not only must Advanced Combat Logging be enabled in the settings, but the logging process itself must be initiated for each game session using the /combatlog chat command. This command acts as a toggle and is deactivated upon logout, disconnect, or client exit. This design creates a significant point of failure, as a user forgetting to re-enable logging will result in incomplete or entirely missing data. The community has developed addon-based solutions like Loggerhead and features within larger addons like DBM to automate this toggle, mitigating the risk of human error.   

Even these automated solutions are not foolproof. Some addons may be configured to cease logging after a Mythic+ boss is defeated, or they may begin logging too late to capture critical initialization events, such as the summoning of a player's permanent pet before a boss pull. Consequently, a parser's architecture must be resilient. It cannot assume that every log file is a perfect, complete record from the start of a session. The developer must anticipate scenarios where initial state information is absent and design heuristics to reconstruct it where possible.   

1.2. The WoWCombatLog.txt File: Format, Location, and Management
The combat log is written to a plain text file named WoWCombatLog.txt, located in the World of Warcraft/_retail_/Logs/ directory. Each line in the file represents a single event, with its constituent data fields separated by commas. While this resembles a standard Comma-Separated Values (CSV) format, it contains structural complexities, such as nested data structures within the advanced parameter fields, that require a more sophisticated parsing strategy than a simple CSV library might offer.   

This file grows continuously as long as logging is active and can quickly become exceptionally large, especially during a long raid session. To manage this, uploader applications and best practices dictate that the file should be processed and then either deleted or archived. This prevents the re-parsing and re-uploading of previously analyzed encounters and ensures efficient operation.   

1.3. The Anatomy of a Log Line: Timestamp, Event Type, and Parameters
Every line in the combat log follows a fundamental structure. It begins with a high-precision timestamp, formatted as a Unix time with millisecond resolution, which serves as the temporal backbone for all analysis. The timestamp is followed by the event type, a string like    

SPELL_DAMAGE, which defines the meaning and order of all subsequent parameters on that line. This dynamic structure is the central challenge for the parser. The log is not a simple table with fixed columns; it is a variable-format stream where the schema of the latter part of a line is determined entirely by the value of its second field.   

Section 2: The Core Parsing Engine: Deconstructing COMBAT_LOG_EVENT_UNFILTERED
The vast majority of meaningful combat data is captured through a single, versatile event structure known within the game's API as COMBAT_LOG_EVENT_UNFILTERED (CLEU). To build a parser, one must first implement a robust grammar for deconstructing this event's many variations.   

2.1. The 11 Base Parameters: The Universal Constants of Every Event
Nearly every combat-related line in the log begins with a consistent set of 11 base parameters. These fields provide the fundamental context for any action: who performed it, who it was directed at, and when it occurred. A parser must be able to reliably extract these fields from every relevant line before attempting to interpret the more dynamic, event-specific data that follows.   

Parameter Index	Parameter Name	Data Type	Description
1	timestamp	Number	Unix timestamp with millisecond precision.
2	subevent	String	The specific combat event type (e.g., SPELL_DAMAGE).
3	hideCaster	Boolean	true if the source of the event is hidden from the log.
4	sourceGUID	String	Globally Unique ID of the source unit.
5	sourceName	String	Name of the source unit.
6	sourceFlags	Number	Bitmask containing metadata about the source unit.
7	sourceRaidFlags	Number	Bitmask for raid target icons on the source unit.
8	destGUID	String	Globally Unique ID of the destination unit.
9	destName	String	Name of the destination unit.
10	destFlags	Number	Bitmask containing metadata about the destination unit.
11	destRaidFlags	Number	Bitmask for raid target icons on the destination unit.

Export to Sheets
Table 2.1: Base Parameters of COMBAT_LOG_EVENT_UNFILTERED    

2.2. Event Prefixes (SWING_, SPELL_, ENVIRONMENTAL_): Identifying the Action's Origin
The subevent string is a composite key that must be deconstructed. The first part, or "prefix," categorizes the fundamental nature of the action. The parser's logic must first identify this prefix to determine the schema of the immediately following parameters.   

SWING_: A standard melee or auto-attack.

SPELL_: An ability originating from a unit's spellbook. This is the most frequently encountered prefix and encompasses the vast majority of class abilities, damage over time effects, and auras.

RANGE_: A ranged weapon attack, such as from a bow or gun, distinct from a spell.

ENVIRONMENTAL_: Damage or an effect originating from the game world itself, such as FALLING, LAVA, or DROWNING.   

For example, events with the SPELL_ prefix are followed by three specific parameters: spellId, spellName, and spellSchool. An    

ENVIRONMENTAL_ prefix is followed by a single environmentalType parameter.

2.3. Event Suffixes (_DAMAGE, _HEAL, _AURA_APPLIED): Understanding the Action's Outcome
The second part of the subevent string, the "suffix," describes the result of the action initiated by the prefix. This suffix dictates the schema for the final set of parameters on the line.   

_DAMAGE: The action successfully dealt health damage.

_HEAL: The action successfully restored health.

_AURA_APPLIED: A beneficial buff or harmful debuff was applied to the destination unit.

_AURA_REMOVED: An existing aura was removed.

_MISSED: The action failed to have its intended effect due to mechanics like DODGE, PARRY, IMMUNE, or ABSORB.

_INTERRUPT: A spell being cast by the destination unit was successfully interrupted.

An event with a _DAMAGE suffix will be followed by a detailed list of parameters describing the damage event, including the amount, any overkill, the damage school (e.g., Fire, Physical), and amounts that were resisted, blocked, or absorbed.   

2.4. Advanced Parameters: A Dynamic Schema Based on Prefixes and Suffixes
The complete parsing logic for a log line is a decision tree. The parser must read the subevent, split it by the last underscore to separate the prefix and suffix, and then apply the correct parameter mapping for each part in sequence. This process is complicated by the fact that the official schema is not publicly documented by Blizzard. The most comprehensive resources are community-maintained wikis, which are subject to becoming outdated as the game is patched. Developers attempting to write parsers have expressed frustration at this lack of official documentation, noting that logs in the live game can contain more parameters for a given event than are listed in community resources.   

This reality has a direct architectural implication: a parser that is hardcoded to expect a fixed number of parameters for each event type is inherently brittle. A robust implementation must be defensive. It should parse the known parameters according to the community-understood grammar but must also be capable of gracefully handling and logging any unexpected trailing parameters without crashing. This approach ensures that the parser will not break with minor game updates and makes it easier to adapt the schema when new data fields are discovered.

2.5. GUIDs and Flags: The Keys to Identifying and Categorizing Combatants
To accurately track combatants, two base parameters are of paramount importance: GUIDs and flags.

GUIDs (Globally Unique Identifiers): The sourceGUID and destGUID are the only reliable method for tracking specific entities throughout a log file. While multiple enemies might share the name "Vile Imp," each will have a unique GUID. The GUID string itself is encoded with information, containing identifiers for the entity's type (Player, Creature, Pet, Vehicle), realm, and a unique serial number.   

Flags: The sourceFlags and destFlags are bitmasks that provide a rich set of metadata about a unit with a single numerical value. By performing bitwise operations, a parser can determine a unit's type (NPC or player), its controller (whether it is mind-controlled or a standard NPC), its reaction (friendly, neutral, or hostile), and its group affiliation (in the player's party, in the player's raid, or an outsider). This information is crucial for correctly attributing actions and filtering data.   

Section 3: Building the World State: Tracking Combatants and Auras
Parsing individual lines is only the first step. To derive meaningful insights, the parser must use these discrete events to construct and maintain a model of the combat state over time. This involves tracking every participant and the dynamic web of status effects that influence their actions.

3.1. The Combatant Roster
The foundation of the state model is a master roster of all combatants involved in the logged encounters. This is best implemented as a dictionary or hash map, where each combatant's GUID serves as the unique key. When a GUID is encountered for the first time in the log, the parser should create a new "combatant" object and populate it with its known information, such as its name and flags. This roster becomes the central repository for tracking dynamic data like current health, resources, and, most importantly, active auras.

3.2. The Aura State Machine: Tracking Buffs, Debuffs, and Stacks
The most complex and critical component of the state model is the aura tracker. Understanding player performance is impossible without the context provided by buffs and debuffs. An ability that deals 100,000 damage is standard under normal conditions but exceptional if performed while under the effect of a major damage-increasing cooldown. The log, being stateless, only provides the moments of application and removal; the parser must maintain the state of "is this aura currently active?" for every combatant.

This is achieved by implementing a state machine. For each combatant in the roster, the parser must maintain a list or dictionary of its currently active auras. When the parser processes an _AURA_APPLIED event, it adds that aura to the target's active list. When it sees an _AURA_REMOVED event, it removes it. Events like _AURA_APPLIED_DOSE modify the stack count of an existing aura in the list. This stateful information is then used to enrich the context of all other events. When a    

SPELL_DAMAGE event occurs, the parser can query the source combatant's active aura list at that exact timestamp to determine which buffs were influencing the attack. This stateful tracking is the core of any advanced analysis and is what enables tools like WoWAnalyzer to perform precise calculations, such as the damage contribution of a Paladin's Devotion Aura to the entire raid. The aura tracking module is not an optional feature; it is central to the parser's ability to provide any analysis beyond raw numbers.   

3.3. Handling Aura Events: _AURA_APPLIED, _REMOVED, _REFRESH, and _DOSE
The logic for the aura state machine is driven by a handful of key event suffixes:

_AURA_APPLIED: Add the specified aura (identified by its spellId) to the destGUID's active aura list. If it is a stacking aura, initialize its stack count (often provided in the amount parameter).

_AURA_REMOVED: Remove the specified aura from the destGUID's active aura list.

_AURA_REFRESH: This event signifies that the duration of an existing aura on destGUID has been reset. The parser should update the timestamp associated with the aura's application.

_AURA_APPLIED_DOSE: This event is used for auras that have stacks. The parser should find the existing aura on destGUID and update its stack count to the new value provided in the amount parameter.

_AURA_REMOVED_DOSE: The inverse of the above; the stack count of an existing aura has been reduced.

3.4. Resource Tracking: Health, Mana, and Other Power Types
The Advanced Combat Log format helpfully includes resource information directly within damage and healing events. For any event with a _DAMAGE or _HEAL suffix, the advanced parameters include the destination unit's current health, maximum health, current primary resource (e.g., mana), and maximum primary resource after the event has resolved. The parser should use this data to continuously update the state of each combatant in its roster. This allows for precise tracking of health percentages over time, which is invaluable for analyzing healer performance, identifying near-death moments, and evaluating a player's ability to handle high-damage mechanics.   

Section 4: Segmenting the Data: Defining Encounters
A raw combat log is a continuous stream of events from an entire game session. To perform analysis, this stream must be segmented into discrete, meaningful units of activity, such as individual boss fights or entire dungeon runs. The parser accomplishes this by watching for specific meta-events that bracket these activities.

4.1. Raid Encounters: Using ENCOUNTER_START and ENCOUNTER_END
For raid boss encounters, the log provides explicit start and end markers. The ENCOUNTER_START event signals the beginning of a pull and provides crucial metadata: the encounterID, the encounterName (e.g., "Raszageth the Storm-Eater"), the difficultyID (e.g., LFR, Normal, Heroic, Mythic), and the groupSize. This event is the trigger for the parser to begin a new "fight" segment.   

The corresponding ENCOUNTER_END event marks the conclusion of the attempt. It contains the same identifying information, along with a boolean success flag (1 for a kill, 0 for a wipe) and the total duration of the encounter in milliseconds. This event signals the parser to close the current fight segment and finalize it for analysis.   

4.2. Mythic+ Dungeons: Using CHALLENGE_MODE_START and CHALLENGE_MODE_END
Mythic+ dungeons are bracketed by a different set of events. A CHALLENGE_MODE_START event is logged when the keystone is activated, marking the beginning of the entire dungeon run. This event provides the zoneName, the instanceID, and the keystoneLevel. The run concludes with a    

CHALLENGE_MODE_END event, which includes a success flag indicating if the timer was met and the total time of the run.

This structure necessitates a more nuanced, hierarchical approach to segmentation compared to raids. While the CHALLENGE_MODE_* events define the overall dungeon, individual boss fights within that dungeon are still marked by their own ENCOUNTER_START and ENCOUNTER_END events. Therefore, a parser designed for Mythic+ analysis must first identify the top-level "Challenge Mode" segment. Within that segment, it can then identify and isolate sub-segments for each boss fight. The periods of activity between the end of one boss encounter and the start of the next can be treated as segments for trash pulls, allowing for a complete breakdown of the entire dungeon run. This hierarchical model is essential for providing a useful and comprehensive Mythic+ analysis.   

4.3. The Concept of a "Fight": Aggregating Events into Analyzable Segments
The output of the segmentation process should be a collection of "Fight" objects. Each object represents a self-contained encounter and serves as the primary unit for analysis. A well-structured Fight object should contain, at a minimum:

A start and end timestamp.

Metadata about the encounter (boss name, difficulty, keystone level, success status).

A list of all combatants (referenced by GUID) who participated.

A chronologically ordered list of all combat log events that occurred within its timeframe.

Section 5: Calculating Effective Performance Metrics
With the log parsed into structured events and segmented into fights, the final step is to calculate meaningful performance metrics. The community has established clear standards for what constitutes "effective" performance, which differ from raw output.

5.1. Effective Damage Per Second (eDPS): The Industry Standard Calculation
The most common metric for damage-dealers is Damage Per Second (DPS). However, the methodology for this calculation is critical.

5.1.1. Defining Fight Duration
For a given encounter segment, the fight duration is the simple delta between the ENCOUNTER_END timestamp and the ENCOUNTER_START timestamp. This is known as the "elapsed time" method.   

5.1.2. Aggregating Damage
To calculate total damage, the parser iterates through all events within the fight segment. It must sum the amount parameter from all event types that represent damage dealt (e.g., SWING_DAMAGE, SPELL_DAMAGE, SPELL_PERIODIC_DAMAGE). This summation should be filtered to only include events where the source is a player (or a player's pet) and the destination is a hostile unit.

5.1.3. The "Active Time" Fallacy vs. Elapsed Time
An alternative calculation method, "active time" DPS, divides total damage by only the time a player spent actively using abilities or waiting for the global cooldown. While this can be a useful diagnostic tool for analyzing a player's rotation, it is not the standard for performance evaluation. The industry standard, as used by premier analysis sites like Warcraft Logs, is    

Effective DPS (eDPS), calculated as:

eDPS= 
Total Fight Duration
Total Damage Dealt
​
 
This elapsed-time method is considered the gold standard because it correctly penalizes downtime. A player who is forced to stop attacking to handle a mechanic, is incapacitated, or dies, will see their eDPS decrease. This provides a more holistic and accurate measure of their actual contribution to defeating the encounter.   

5.2. Effective Healing Per Second (eHPS): A Measure of Useful Throughput
For healers, simply measuring raw healing output is misleading. The crucial metric is "effective" healing—healing that actually restores a target's missing health.

5.2.1. The Role of overhealing in _HEAL Events
The _HEAL event suffix in the Advanced Combat Log provides two key values: the total amount healed and the overhealing amount. Overhealing is any portion of a heal that lands on a target that is already at full health. Effective healing from a single event is therefore    

amount - overhealing.

5.2.2. Incorporating Damage Absorbs as Effective Healing
A significant portion of some healers' contribution comes from damage-absorbing shields. When damage is prevented by a shield, a SPELL_ABSORBED event is generated. The    

absorbedAmount from this event represents damage that was prevented and must be credited to the caster of the absorbing spell as effective healing.

5.2.3. Total Healing vs. Effective Healing: A Critical Distinction
The final formula for a healer's contribution is Effective Healing Per Second (eHPS):

$$ eHPS = \frac{(\sum (\text{Heal Amount} - \text{Overhealing})) + (\sum \text{Absorb Amount})}{\text{Total Fight Duration}} $$

This metric is far more valuable than raw HPS. High raw HPS combined with high overhealing is often a sign of inefficiency, such as poor mana management or casting large heals on targets that only need minor healing. eHPS measures a healer's true impact on the group's survival.   

Section 6: Advanced Parsing Logic and Edge Case Handling
Beyond the fundamentals, a truly robust parser must handle a variety of complex scenarios and edge cases that require careful state management and logical inference.

6.1. Damage over Time (DoTs) and Healing over Time (HoTs): SPELL_PERIODIC_* Events
The combat log provides specific event types for periodic effects, such as SPELL_PERIODIC_DAMAGE and SPELL_PERIODIC_HEAL. These are parsed similarly to their direct-damage counterparts but should be categorized separately. This allows for advanced analysis specific to these mechanics, such as calculating the uptime of a crucial DoT on a target or the efficiency of a HoT-based healing style.

6.2. Pet and Guardian Attribution: Mapping Actions to Owners
A common challenge is correctly attributing the actions of pets, guardians, and other summoned units to their owners.

6.2.1. The _SUMMON Event and Establishing Ownership
The primary mechanism for establishing this link is the SPELL_SUMMON event. When a player casts a summoning spell, this event is logged. The sourceGUID is the owner, and the destGUID is the newly summoned pet. The parser must capture this GUID pair and store it in a persistent map. For the remainder of the log, any action originating from the pet's GUID can be correctly attributed to the owner's total damage or healing.

6.2.2. Handling "Orphaned" Pets in Incomplete Logs
A frequent failure mode occurs when logging begins after a player has already summoned their permanent pet. In this scenario, the    

SPELL_SUMMON event is missing from the log, and the pet's actions are "orphaned," with no explicit link to its owner. This can lead to pet damage being misattributed or ignored entirely.   

To solve this, the parser must implement a heuristic. The Advanced Combat Log includes a COMBATANT_INFO event, which is logged periodically for units in combat and contains an ownerGUID field for pets and guardians. If the parser encounters an action from an unknown pet GUID, it can search for a COMBATANT_INFO event associated with that pet to retroactively establish the ownership link. This defensive programming is essential for handling the realities of imperfect log files.

6.3. Nuances of Healing and Damage Mitigation
The interplay between damage and healing is complex, involving several distinct mechanics that must be parsed correctly.

6.3.1. Parsing Damage Shields: SPELL_ABSORBED
When damage is prevented by a shield, a SPELL_ABSORBED event is generated. This event is unique in that it contains information about two spells: the spell that dealt the damage and the spell that created the absorbing shield. The parser must identify the    

absorbSpellId and credit the absorbedAmount to the caster of that shield as effective healing.

6.3.2. Parsing Healing Absorbs: SPELL_HEAL_ABSORBED
A separate and critically important event is SPELL_HEAL_ABSORBED. This event occurs when a healing spell is "consumed" by a debuff on the target that prevents healing. This is the opposite of effective healing; it is healing that was nullified. A comprehensive parser must track these events to accurately model a target's health and understand situations where a player's health fails to increase despite being the target of healing spells.   

6.3.3. Distinguishing Between Mitigated, Resisted, and Blocked Damage
The _DAMAGE event suffix provides separate fields for damage that was resisted, blocked, and absorbed. It is important to distinguish these:   

Absorbed damage is prevented by a shield cast by another player (or oneself) and is counted as healing for the caster of the shield.

Resisted damage is a reduction due to the target's own magical resistances.

Blocked damage is a reduction due to the target using a physical shield item.

Resisted and blocked damage are forms of self-mitigation by the target, whereas absorbed damage is a contribution from another unit.

Conclusion
Developing a World of Warcraft combat log parser is a significant undertaking that extends beyond simple file I/O. It requires the implementation of a robust state machine capable of reconstructing the complex, second-by-second state of a combat encounter from a raw stream of events. The architectural cornerstones of such a system are: a defensive parsing strategy that can accommodate an evolving and unofficially documented log format; a stateful model centered on a combatant roster and a meticulous aura tracker; and a hierarchical segmentation engine that can distinguish between different content types like raids and Mythic+ dungeons.

By adhering to the community-defined standards for calculating effective performance metrics like eDPS and eHPS, a developer can transform the cryptic lines of WoWCombatLog.txt into a powerful tool for analysis. The next steps in such a project typically involve designing a data storage strategy for the parsed information—whether outputting to structured JSON files or loading into a database like SQLite—and building a user interface that allows for intuitive querying and visualization of the results, ultimately empowering players to understand and improve their gameplay.


Sources used in the report

archon.gg
Getting Started | Archon (WoW - TWW)
Opens in a new window

us.forums.blizzard.com
Is there a way to capture the combat log? - General Discussion - World of Warcraft Forums
Opens in a new window

warcraftlogs.com
Getting Started With Warcraft Logs
Opens in a new window

classic.warcraftlogs.com
Getting Started With Warcraft Logs
Opens in a new window

reddit.com
[Guide] How to create and upload combat logs to WarcraftLogs for analysis! - Reddit
Opens in a new window

warcraft.wiki.gg
COMBAT_LOG_EVENT - Warcraft Wiki - Your wiki guide to the World of Warcraft
Opens in a new window

reddit.com
Questions about combat logging. : r/wow - Reddit
Opens in a new window

github.com
dratr/loggerhead: Automatic combat log enabler for WoW - GitHub
Opens in a new window

forums.combatlogforums.com
Combat Log Stops Recording After First Boss in Mythic+ - Any Solutions? - Warcraft Logs
Opens in a new window

reddit.com
Quick access to any data from your Combat Log files : r/CompetitiveWoW - Reddit
Opens in a new window

reddit.com
Is there a program that makes the combat log human readable? : r/wow - Reddit
Opens in a new window

wowinterface.com
Combat_Log_Event simple explanation please.. - WoWInterface
Opens in a new window

addonstudio.org
WoW:API COMBAT LOG EVENT - AddOn Studio
Opens in a new window

us.forums.blizzard.com
Advanced Combat Log Documentation Requested - General Discussion - Blizzard Forums
Opens in a new window

us.forums.blizzard.com
WoWCombatLog.txt - General Discussion - World of Warcraft Forums
Opens in a new window

warcraft.wiki.gg
CombatLog_Object_IsA - Warcraft Wiki - Your wiki guide to the World of Warcraft
Opens in a new window

github.com
WoWAnalyzer/CombatLogParser: A WoW combatlog parser by WoWAnalyzer. - GitHub
Opens in a new window

us.forums.blizzard.com
Dungeons should have EncounterIds - WoW Classic General Discussion - Blizzard Forums
Opens in a new window

us.forums.blizzard.com
Determine Out-of-Combat State - UI and Macro - World of Warcraft Forums
Opens in a new window

reddit.com
Warcraft Recorder: a lightweight, free, no-fuss application to record and play back your encounters. : r/CompetitiveWoW - Reddit
Opens in a new window

reddit.com
[WoW Explained] DPS Calculation Confusion: Active Time vs. Elapsed Time - Reddit
Opens in a new window

itsbetteronthebeach.com
WoW Raid Log Analysis by Class: Combat Logs & Metrics - itsbetteronthebeach
Opens in a new window

blog.askmrrobot.com
Combat Log Preview: Healer & Tank Overview - Ask Mr. Robot
Opens in a new window

us.forums.blizzard.com
How do I find my HPS? - General Discussion - World of Warcraft Forums
Opens in a new window

forums.combatlogforums.com
Pet damage showing up weird - Warcraft Logs
Opens in a new window

wowinterface.com
Combatlog: Where is the _ABSORBED suffix? - WoWInterface
Opens in a new window

us.forums.blizzard.com
Ray of Hope WeakAura no longer works - UI and Macro - World of Warcraft Forums