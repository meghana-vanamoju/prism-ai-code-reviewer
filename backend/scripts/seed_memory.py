#!/usr/bin/env python3
"""
Seed script to populate Hindsight with demo memories for PRISM.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.config import settings
from app.services.hindsight_service import HindsightService
from app.models.memory import RetainMemoryRequest


def main():
    seed_file = Path(__file__).parent.parent.parent / "demo-data" / "seed_memories.json"

    if not seed_file.exists():
        print(f"ERROR: Seed file not found: {seed_file}")
        sys.exit(1)

    with open(seed_file, "r") as f:
        memories = json.load(f)

    print(f"Seeding PRISM memory bank: {settings.hindsight_bank_id}")
    print(f"Hindsight URL: {settings.hindsight_base_url}")
    print(f"Loading {len(memories)} memories from {seed_file}")
    print()

    service = HindsightService()

    success_count = 0
    for i, memory in enumerate(memories, 1):
        try:
            content_preview = memory["content"][:60] + "..." if len(memory["content"]) > 60 else memory["content"]
            print(f"[{i}/{len(memories)}] Retaining: {content_preview}")

            response = service.retain_memory(
                RetainMemoryRequest(
                    content=memory["content"],
                    context=memory.get("context"),
                    metadata=memory.get("metadata"),
                )
            )

            if response.success:
                print(f"      ✓ Success (items: {response.items_count})")
                success_count += 1
            else:
                print(f"      ✗ Failed: {response}")
        except Exception as e:
            print(f"      ✗ Error: {e}")

    print()
    print(f"Memory seeding complete: {success_count}/{len(memories)} succeeded")

    if success_count < len(memories):
        sys.exit(1)


if __name__ == "__main__":
    main()