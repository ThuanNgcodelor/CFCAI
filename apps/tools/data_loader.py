from __future__ import annotations

import argparse
import json

from src.chatbot.core.settings import settings
from src.chatbot.infrastructure.db.migrations import apply_migrations
from src.chatbot.modules.integrations.data_loader import DataSourceLoader, json_ready
from src.chatbot.modules.integrations.excel.repository import CatalogPublishRepository
from src.chatbot.shared.enums import PageCode


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate and publish configured data sources"
    )
    parser.add_argument(
        "--manifest",
        default=settings.DATA_SOURCE_MANIFEST_PATH,
        help="Source manifest path",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    validate = commands.add_parser("validate")
    validate.add_argument("--all", action="store_true")
    stage = commands.add_parser("stage")
    stage.add_argument("--changed", action="store_true")
    stage.add_argument("--actor", default="data-loader")
    status = commands.add_parser("status")
    status.add_argument("--page", choices=[item.value for item in PageCode])
    status.add_argument("--limit", type=int, default=50)
    for name in ("approve", "reject", "publish"):
        command = commands.add_parser(name)
        command.add_argument(
            "--page", required=True, choices=[item.value for item in PageCode]
        )
        command.add_argument("--batch", required=True)
        command.add_argument("--actor", required=True)
    rollback = commands.add_parser("rollback")
    rollback.add_argument(
        "--page", required=True, choices=[item.value for item in PageCode]
    )
    rollback.add_argument("--version", required=True, type=int)
    rollback.add_argument("--actor", required=True)
    return parser


def main() -> int:
    args = _parser().parse_args()
    database_url = settings.get_database_url()
    if args.command == "validate":
        result = DataSourceLoader(args.manifest).validate()
    else:
        apply_migrations(database_url)
        repository = CatalogPublishRepository(database_url)
        loader = DataSourceLoader(args.manifest, repository)
        if args.command == "stage":
            result = loader.stage_changed(actor=args.actor)
        elif args.command == "status":
            page = PageCode(args.page) if args.page else None
            result = repository.list_batches(page, limit=args.limit)
        elif args.command == "approve":
            result = {
                "approved_count": repository.approve_batch(
                    PageCode(args.page), args.batch, actor=args.actor
                )
            }
        elif args.command == "reject":
            result = {
                "rejected_count": repository.reject_batch(
                    PageCode(args.page), args.batch, actor=args.actor
                )
            }
        elif args.command == "publish":
            result = {
                "version": repository.publish_batch(
                    PageCode(args.page), args.batch, actor=args.actor
                )
            }
        else:
            result = {
                "batch_id": repository.rollback(
                    PageCode(args.page), args.version, actor=args.actor
                )
            }
    print(json.dumps(json_ready(result), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
