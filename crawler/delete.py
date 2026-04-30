#!/usr/bin/env python3
"""Delete finished stories from local data.

Usage:
    python -m crawler.delete                  # Interactive selection
    python -m crawler.delete --list            # List all stories
    python -m crawler.delete <story-slug>      # Delete specific story
    python -m crawler.delete --all-read        # Delete all stories (with confirm)
"""
import argparse
import json
import shutil
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"


def list_stories() -> list[dict]:
    """Scan data directory and return list of stories with metadata."""
    stories = []
    for site_dir in sorted(DATA_DIR.iterdir()):
        if not site_dir.is_dir() or site_dir.name.startswith("."):
            continue
        for story_dir in sorted(site_dir.iterdir()):
            if not story_dir.is_dir():
                continue
            meta_path = story_dir / "metadata.json"
            title = story_dir.name
            if meta_path.exists():
                try:
                    with open(meta_path, "r", encoding="utf-8") as f:
                        meta = json.load(f)
                    title = meta.get("story_title", title)
                except (json.JSONDecodeError, OSError):
                    pass
            size_mb = sum(f.stat().st_size for f in story_dir.rglob("*") if f.is_file()) / (1024 * 1024)
            vol_count = len(list(story_dir.glob("vol-*.json")))
            stories.append({
                "slug": story_dir.name,
                "site": site_dir.name,
                "title": title,
                "path": story_dir,
                "size_mb": round(size_mb, 1),
                "volumes": vol_count,
            })
    return stories


def print_stories(stories: list[dict]) -> None:
    for i, s in enumerate(stories, 1):
        print(f"  [{i}] {s['title']}")
        print(f"      Site: {s['site']}  |  {s['volumes']} volumes  |  {s['size_mb']} MB")
        print(f"      Slug: {s['slug']}")
        print()


def delete_story(story: dict) -> None:
    shutil.rmtree(story["path"])
    print(f"Deleted: {story['title']} ({story['size_mb']} MB)")


def interactive_select(stories: list[dict]) -> None:
    if not stories:
        print("No stories found.")
        return

    print("Available stories:\n")
    print_stories(stories)
    print("Enter numbers to delete (comma-separated), or 'q' to quit:")
    choice = input("> ").strip()
    if choice.lower() == "q":
        return

    try:
        indices = [int(x.strip()) for x in choice.split(",")]
    except ValueError:
        print("Invalid input.")
        return

    to_delete = []
    for idx in indices:
        if 1 <= idx <= len(stories):
            to_delete.append(stories[idx - 1])
        else:
            print(f"Skipping invalid index: {idx}")

    if not to_delete:
        print("Nothing selected.")
        return

    print("\nWill delete:")
    for s in to_delete:
        print(f"  - {s['title']} ({s['size_mb']} MB)")
    total = sum(s["size_mb"] for s in to_delete)
    print(f"Total: {len(to_delete)} stories, {round(total, 1)} MB")

    confirm = input("\nConfirm? (y/N): ").strip().lower()
    if confirm == "y":
        for s in to_delete:
            delete_story(s)
        print(f"\nDone. Freed {round(total, 1)} MB.")
    else:
        print("Cancelled.")


def main():
    parser = argparse.ArgumentParser(description="Delete crawled stories")
    parser.add_argument("--list", action="store_true", help="List all stories")
    parser.add_argument("slugs", nargs="*", help="Story slugs to delete")
    args = parser.parse_args()

    stories = list_stories()

    if args.list:
        if not stories:
            print("No stories found.")
        else:
            print_stories(stories)
        return

    if args.slugs:
        to_delete = [s for s in stories if s["slug"] in args.slugs]
        not_found = set(args.slugs) - {s["slug"] for s in to_delete}
        if not_found:
            print(f"Not found: {', '.join(not_found)}")
        if not to_delete:
            return
        print("Will delete:")
        for s in to_delete:
            print(f"  - {s['title']} ({s['size_mb']} MB)")
        confirm = input("Confirm? (y/N): ").strip().lower()
        if confirm == "y":
            for s in to_delete:
                delete_story(s)
        else:
            print("Cancelled.")
        return

    interactive_select(stories)


if __name__ == "__main__":
    main()
