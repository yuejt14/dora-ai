"""CLI chat loop — multi-turn conversation with persistence."""

import sys

from backend.async_bridge import AsyncBridge
from backend.config import AppSettings, setup_logging
from backend.conversation import ConversationPipeline
from backend.db.database import Database
from backend.providers.router import ProviderRouter


def main() -> None:
    settings = AppSettings()
    setup_logging(settings.log_level)

    db = Database()
    db.connect()
    db.run_migrations()

    router = ProviderRouter(settings.provider)
    bridge = AsyncBridge()
    bridge.start()

    # Check provider availability
    provider = router.get()
    if not bridge.run(provider.is_available()):
        print(
            f"Error: {settings.provider.active} is not reachable. "
            "Check that the provider is running and configured correctly."
        )
        bridge.stop()
        db.close()
        sys.exit(1)

    print(f"Connected to {settings.provider.active} ({settings.provider.ollama.model})")

    pipeline = ConversationPipeline(db, router, bridge)

    try:
        conversation_id = _select_conversation(pipeline)
        _chat_loop(pipeline, conversation_id)
    except KeyboardInterrupt:
        print("\nBye!")
    except EOFError:
        print("\nBye!")
    finally:
        bridge.run(router.close())
        bridge.stop()
        db.close()


def _select_conversation(pipeline: ConversationPipeline) -> str:
    """Let user pick an existing conversation or create a new one."""
    conversations = pipeline.list_conversations()

    if conversations:
        print("\nExisting conversations:")
        for i, conv in enumerate(conversations, 1):
            print(f"  {i}. {conv['title']} ({conv['id'][:8]}...)")
        print(f"  {len(conversations) + 1}. New conversation")
        print()

        while True:
            choice = input("Pick a conversation (number): ").strip()
            if not choice:
                continue
            try:
                idx = int(choice)
            except ValueError:
                continue
            if 1 <= idx <= len(conversations):
                conv = conversations[idx - 1]
                print(f"Resuming: {conv['title']}")
                return conv["id"]
            if idx == len(conversations) + 1:
                break

    title = input("Conversation title (enter to skip): ").strip() or None
    conv_id = pipeline.create_conversation(title)
    print(f"Started new conversation ({conv_id[:8]}...)")
    return conv_id


def _chat_loop(pipeline: ConversationPipeline, conversation_id: str) -> None:
    """Read input, stream response, repeat."""
    print("\nCommands: /new, /history, /quit")
    print("---")

    while True:
        try:
            text = input("\nYou: ").strip()
        except KeyboardInterrupt:
            raise
        except EOFError:
            raise

        if not text:
            continue

        if text == "/quit":
            break
        if text == "/new":
            conversation_id = _new_conversation(pipeline)
            continue
        if text == "/history":
            _show_history(pipeline, conversation_id)
            continue

        # Stream response
        print("\nAssistant: ", end="", flush=True)
        for chunk in pipeline.send_message(conversation_id, text):
            print(chunk, end="", flush=True)
        print()


def _new_conversation(pipeline: ConversationPipeline) -> str:
    title = input("Title (enter to skip): ").strip() or None
    conv_id = pipeline.create_conversation(title)
    print(f"Started new conversation ({conv_id[:8]}...)")
    return conv_id


def _show_history(pipeline: ConversationPipeline, conversation_id: str) -> None:
    messages = pipeline.get_history(conversation_id)
    if not messages:
        print("(no messages yet)")
        return
    print()
    for msg in messages:
        prefix = "You" if msg.role == "user" else "Assistant"
        print(f"{prefix}: {msg.content}")


if __name__ == "__main__":
    main()
