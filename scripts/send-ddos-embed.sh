#!/usr/bin/env bash

set -euo pipefail

WEBHOOK_URL="${1:-}"
INPUT_FILE="${2:-}"

if [[ -z "$WEBHOOK_URL" || -z "$INPUT_FILE" ]]; then
    echo "Usage: $0 <webhook_url> <ddos_event.json>"
    exit 1
fi

if [[ ! -f "$INPUT_FILE" ]]; then
    echo "❌ File not found: $INPUT_FILE"
    exit 1
fi

if ! command -v jq >/dev/null 2>&1; then
    echo "❌ jq is required."
    exit 1
fi

if ! command -v curl >/dev/null 2>&1; then
    echo "❌ curl is required."
    exit 1
fi


echo "🔎 Reading DDoS event..."

PAYLOAD="$(
jq '
    # ---------------------------------------------------------
    # Find the source with the highest packet rate
    # ---------------------------------------------------------

    (.sources | sort_by(.packets_per_second // 0) | reverse | .[0]) as $primary |

    # ---------------------------------------------------------
    # Find sources with previous correlations
    # ---------------------------------------------------------

    (
        .sources
        | map(
            select(
                .correlation.has_player_match == true
                or .correlation.has_rcon_match == true
                or .correlation.has_ssh_match == true
            )
        )
    ) as $correlated |

    # ---------------------------------------------------------
    # Main event information
    # ---------------------------------------------------------

    . as $event |

    {
        username: "JTWP Network Monitor",

        embeds: [
            {
                title: "⚠️ Possible DDoS Activity Detected",

                description:
                    (
                        "A network traffic spike triggered the JTWP DDoS detector.\n\n" +

                        "**Severity:** `" +
                        (($event.severity // "unknown") | tostring) +
                        "`\n" +

                        "**Detection Only:** `" +
                        (($event.detection_only // false) | tostring) +
                        "`\n" +

                        "**Automatic Blocking:** `" +
                        (($event.automatic_blocking // false) | tostring) +
                        "`\n\n" +

                        "**Traffic Window**\n" +

                        "Packets: `" +
                        (($event.packets // 0) | tostring) +
                        "`\n" +

                        "Window: `" +
                        (($event.window_seconds // 0) | tostring) +
                        " seconds`\n" +

                        "Packet Rate: `" +
                        (($event.packets_per_second // 0) | tostring) +
                        " packets/sec`\n" +

                        "Unique Sources: `" +
                        (($event.unique_sources // 0) | tostring) +
                        "`\n" +

                        "Highest Single Source: `" +
                        (($event.highest_source_packets_per_second // 0) | tostring) +
                        " packets/sec`"
                    ),

                color: 16753920,

                fields:

                    # -------------------------------------------------
                    # PRIMARY SOURCE
                    # -------------------------------------------------

                    [
                        {
                            name: "🚨 Primary High-Volume Source",

                            value:
                                (
                                    "**IP Hash**\n`" +
                                    ($primary.ip_hash // "Unknown") +
                                    "`\n\n" +

                                    "**Traffic**\n" +

                                    "Packets: `" +
                                    (($primary.packets // 0) | tostring) +
                                    "`\n" +

                                    "Rate: `" +
                                    (($primary.packets_per_second // 0) | tostring) +
                                    " packets/sec`\n" +

                                    "Destination Ports: `" +

                                    (
                                        (
                                            $primary.destination_ports
                                            // {}
                                            | keys
                                            | join(", ")
                                        )
                                    ) +

                                    "`\n\n" +

                                    "**Correlation**\n" +

                                    "Player History: " +
                                    (
                                        if $primary.correlation.has_player_match
                                        then "✅ Found"
                                        else "❌ None"
                                        end
                                    ) +

                                    "\nRCON History: " +
                                    (
                                        if $primary.correlation.has_rcon_match
                                        then "✅ Found"
                                        else "❌ None"
                                        end
                                    ) +

                                    "\nSSH History: " +
                                    (
                                        if $primary.correlation.has_ssh_match
                                        then "✅ Found"
                                        else "❌ None"
                                        end
                                    ) +

                                    "\n\n⚠️ This source generated the highest packet rate and should be investigated first."
                                ),

                            inline: false
                        }
                    ]

                    +

                    # -------------------------------------------------
                    # CORRELATED SOURCES
                    # -------------------------------------------------

                    (
                        $correlated

                        | to_entries

                        | map(

                            .key as $index |
                            .value as $source |

                            {
                                name:
                                    (
                                        "🔎 Correlated Source #" +
                                        (($index + 1) | tostring)
                                    ),

                                value:
                                    (
                                        "**IP Hash**\n`" +
                                        ($source.ip_hash // "Unknown") +
                                        "`\n\n" +

                                        "**Traffic During Event**\n" +

                                        "Packets: `" +
                                        (($source.packets // 0) | tostring) +
                                        "`\n" +

                                        "Rate: `" +
                                        (($source.packets_per_second // 0) | tostring) +
                                        " packets/sec`\n\n" +

                                        "**Previous Activity**\n" +

                                        "Player Match: " +
                                        (
                                            if $source.correlation.has_player_match
                                            then "✅"
                                            else "❌"
                                            end
                                        ) +

                                        "\nRCON Match: " +
                                        (
                                            if $source.correlation.has_rcon_match
                                            then "✅"
                                            else "❌"
                                            end
                                        ) +

                                        "\nSSH Match: " +
                                        (
                                            if $source.correlation.has_ssh_match
                                            then "✅"
                                            else "❌"
                                            end
                                        ) +

                                        (
                                            if (
                                                ($source.correlation.rcon_matches // [])
                                                | length
                                            ) > 0
                                            then

                                                "\n\n**RCON History**\n" +

                                                (
                                                    $source.correlation.rcon_matches

                                                    | map(
                                                        "`" +
                                                        (.server_id // "Unknown") +
                                                        "` — " +
                                                        (.kind // "unknown") +
                                                        " | Success: `" +
                                                        ((.successful_connections // 0) | tostring) +
                                                        "` | Failed: `" +
                                                        ((.failed_attempts // 0) | tostring) +
                                                        "`"
                                                    )

                                                    | join("\n")
                                                )

                                            else
                                                ""
                                            end
                                        )

                                        +

                                        (
                                            if $source.correlation.ssh_match != null
                                            then

                                                "\n\n**SSH History**\n" +

                                                "Failed Attempts: `" +
                                                (
                                                    (
                                                        $source.correlation.ssh_match.failed_attempts
                                                        // 0
                                                    )
                                                    | tostring
                                                ) +

                                                "`\nBlocked: `" +

                                                (
                                                    (
                                                        $source.correlation.ssh_match.blocked
                                                        // false
                                                    )
                                                    | tostring
                                                ) +

                                                "`"

                                            else
                                                ""
                                            end
                                        )
                                    ),

                                inline: false
                            }
                        )
                    )

                    +

                    # -------------------------------------------------
                    # FINAL WARNING
                    # -------------------------------------------------

                    [
                        {
                            name: "🧠 Investigation Summary",

                            value:
                                (
                                    "**Primary Source**\n`" +
                                    ($primary.ip_hash // "Unknown") +
                                    "`\n\n" +

                                    "Generated `" +
                                    (($primary.packets // 0) | tostring) +
                                    " / " +
                                    (($event.packets // 0) | tostring) +
                                    "` packets observed during this event.\n\n" +

                                    "**Historical Correlations:** `" +
                                    (($correlated | length) | tostring) +
                                    "` source(s)\n\n" +

                                    "⚠️ An IP-hash correlation means the same network address was previously observed by another JTWP data source. It does not prove that a Player, RCON user, or SSH user generated the suspicious traffic."
                                ),

                            inline: false
                        }
                    ],

                footer: {
                    text:
                        "JTWP Network Abuse Monitor • Correlation does not prove attribution"
                },

                timestamp: $event.timestamp
            }
        ]
    }
' "$INPUT_FILE"
)"


echo "📤 Sending Discord embed..."


RESPONSE="$(
    curl -sS \
        -w $'\n%{http_code}' \
        -H "Content-Type: application/json" \
        -X POST \
        -d "$PAYLOAD" \
        "$WEBHOOK_URL"
)"


HTTP_CODE="$(
    printf '%s\n' "$RESPONSE" |
    tail -n 1
)"

BODY="$(
    printf '%s\n' "$RESPONSE" |
    sed '$d'
)"


if [[ "$HTTP_CODE" == "204" || "$HTTP_CODE" == "200" ]]; then

    echo "✅ DDoS report sent successfully."
    echo "Discord HTTP: $HTTP_CODE"

else

    echo "❌ Discord webhook failed."
    echo "HTTP: $HTTP_CODE"

    if [[ -n "$BODY" ]]; then
        echo "$BODY"
    fi

    exit 1

fi
