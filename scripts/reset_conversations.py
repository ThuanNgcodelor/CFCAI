#!/usr/bin/env python3
"""Utility script to reset conversation history and slot memory for testing.

Preserves catalog_items, faq_items, knowledge_records, and publications.
Usage:
    python scripts/reset_conversations.py [--sender-id SENDER_ID] [--all]
"""

import argparse
import sys
import psycopg2
from chatbot.infrastructure.config import load_settings


def reset_conversations(sender_id: str | None = None, reset_all: bool = False) -> None:
    settings = load_settings()
    conn = psycopg2.connect(settings.database_url)
    conn.autocommit = False

    try:
        with conn.cursor() as cur:
            if sender_id:
                print(f"[*] Resetting conversation for sender: {sender_id}")
                cur.execute(
                    """
                    DELETE FROM conversation_slots
                    WHERE conversation_id IN (
                        SELECT conversation_id FROM conversations WHERE sender_id = %s
                    )
                    """,
                    (sender_id,),
                )
                cur.execute(
                    """
                    DELETE FROM conversation_messages
                    WHERE conversation_id IN (
                        SELECT conversation_id FROM conversations WHERE sender_id = %s
                    )
                    """,
                    (sender_id,),
                )
                cur.execute(
                    """
                    DELETE FROM message_batches
                    WHERE conversation_id IN (
                        SELECT conversation_id FROM conversations WHERE sender_id = %s
                    )
                    """,
                    (sender_id,),
                )
                cur.execute(
                    """
                    DELETE FROM handoff_events
                    WHERE conversation_id IN (
                        SELECT conversation_id FROM conversations WHERE sender_id = %s
                    )
                    """,
                    (sender_id,),
                )
                cur.execute("DELETE FROM outbox_messages WHERE recipient_id = %s", (sender_id,))
                cur.execute("DELETE FROM inbox_events WHERE sender_id = %s", (sender_id,))
                cur.execute("DELETE FROM conversations WHERE sender_id = %s", (sender_id,))
            elif reset_all:
                print("[*] Resetting ALL conversations, slots, and message history...")
                cur.execute("DELETE FROM conversation_slots;")
                cur.execute("DELETE FROM conversation_messages;")
                cur.execute("DELETE FROM handoff_events;")
                cur.execute("DELETE FROM message_batches;")
                cur.execute("DELETE FROM outbox_messages;")
                cur.execute("DELETE FROM inbox_events;")
                cur.execute("DELETE FROM conversations;")
            else:
                print("Error: Specify --sender-id <id> or --all")
                sys.exit(1)

        conn.commit()
        print("[✓] Successfully reset conversation data.")
    except Exception as e:
        conn.rollback()
        print(f"[✗] Error during reset: {e}")
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Reset conversation state for testing")
    parser.add_argument("--sender-id", help="Reset specific PSID/sender_id")
    parser.add_argument("--all", action="store_true", help="Reset all conversations")
    args = parser.parse_args()

    if not args.sender_id and not args.all:
        args.all = True

    reset_conversations(sender_id=args.sender_id, reset_all=args.all)
