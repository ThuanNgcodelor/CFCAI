"""Reset chat-runtime data for a fresh test conversation.

This deliberately preserves approved knowledge/catalog data, CRM snapshots and the
append-only operational audit.  It only removes state that can make the next chat
look like a continuation: inbox/outbox records, conversation memory, batches and
customer handoff tasks.

Usage:
    python apps/tools/reset_conversations.py [--sender-id SENDER_ID] [--all]
"""

import argparse
import sys

import psycopg2

from src.chatbot.core.settings import settings

# Every table here either references ``conversations`` or contains transient
# delivery state keyed by its conversation ID.  The order is intentional:
# ``handoff_tasks`` was introduced after this tool and has a foreign key to
# ``conversations``, so it must be removed before its parent row.
_CONVERSATION_STATE_TABLES = (
    "handoff_tasks",
    "handoff_events",
    "conversation_slots",
    "conversation_messages",
    "message_batches",
    "outbox_messages",
)


def _delete_sender_conversation_state(cur, sender_id: str) -> None:
    """Delete transient state for every page-scoped conversation of one sender."""
    for table_name in _CONVERSATION_STATE_TABLES:
        cur.execute(
            f"""
            DELETE FROM {table_name}
            WHERE conversation_id IN (
                SELECT conversation_id FROM conversations WHERE sender_id = %s
            )
            """,
            (sender_id,),
        )

    # Inbox events can exist before a conversation was created, so they must be
    # deleted directly by sender instead of through the conversation subquery.
    cur.execute("DELETE FROM inbox_events WHERE sender_id = %s", (sender_id,))
    cur.execute("DELETE FROM conversations WHERE sender_id = %s", (sender_id,))


def _delete_all_conversation_state(cur) -> None:
    """Delete all transient chat state in foreign-key-safe order."""
    for table_name in _CONVERSATION_STATE_TABLES:
        cur.execute(f"DELETE FROM {table_name};")
    cur.execute("DELETE FROM inbox_events;")
    cur.execute("DELETE FROM conversations;")


def reset_conversations(sender_id: str | None = None, reset_all: bool = False) -> None:
    db_url = (
        settings.get_database_url()
        .replace("postgresql+asyncpg://", "postgresql://")
        .replace("postgresql+psycopg2://", "postgresql://")
    )
    conn = psycopg2.connect(db_url)
    conn.autocommit = False

    try:
        with conn.cursor() as cur:
            if sender_id:
                print(f"[*] Resetting conversation for sender: {sender_id}")
                _delete_sender_conversation_state(cur, sender_id)
            elif reset_all:
                print("[*] Resetting ALL conversations, slots, and message history...")
                _delete_all_conversation_state(cur)
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
