"""
label-speakers.py - Post-process WhisperX JSON output to produce a labeled transcript.

Usage:
    python label-speakers.py <input.json> <output.txt> [--hosts Rocket Trog]

WhisperX diarization assigns anonymous speaker IDs (SPEAKER_00, SPEAKER_01, etc.).
This script figures out who is who by showing you sample lines from each speaker,
then asks you to label them. Rocket and Trog are the default hosts; you can add
guest names at the prompt.
"""

import json
import sys
import argparse
import os
from collections import defaultdict

DEFAULT_HOSTS = ["Rocket", "Trog"]
UNKNOWN_LABEL = "Unknown"


def load_whisperx_json(path):
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data


def gather_speaker_samples(segments, max_samples=5):
    """Return a dict of speaker_id -> list of sample text snippets."""
    samples = defaultdict(list)
    for seg in segments:
        speaker = seg.get("speaker", UNKNOWN_LABEL)
        text = seg.get("text", "").strip()
        if text and len(samples[speaker]) < max_samples:
            samples[speaker].append(text)
    return samples


def prompt_speaker_labels(samples, default_hosts):
    """
    Interactively ask the user to label each speaker.
    Shows sample lines and suggests host names.
    Returns a dict of speaker_id -> display_name.
    """
    speaker_ids = sorted(samples.keys())
    remaining_hosts = list(default_hosts)
    mapping = {}

    print()
    print("=" * 60)
    print("  SPEAKER IDENTIFICATION")
    print("=" * 60)
    print(f"  Found {len(speaker_ids)} speaker(s) in this recording.")
    print()

    for i, speaker_id in enumerate(speaker_ids):
        print(f"--- Speaker: {speaker_id} ---")
        print("  Sample lines:")
        for line in samples[speaker_id]:
            # Truncate long lines for readability
            preview = line if len(line) <= 80 else line[:77] + "..."
            print(f"    \"{preview}\"")
        print()

        # Build a suggestion prompt
        if remaining_hosts:
            suggestion = remaining_hosts[0]
            hosts_hint = " / ".join(remaining_hosts)
            prompt_text = f"  Name this speaker [{hosts_hint}] (Enter for '{suggestion}', or type a name): "
        else:
            prompt_text = f"  Name this speaker (e.g. GuestName, or Enter for '{UNKNOWN_LABEL}'): "
            suggestion = UNKNOWN_LABEL

        raw = input(prompt_text).strip()

        if raw == "":
            label = suggestion
        else:
            label = raw

        mapping[speaker_id] = label

        # Remove this label from remaining_hosts if it was one of them
        if label in remaining_hosts:
            remaining_hosts.remove(label)

        print(f"  -> Labeled as: {label}")
        print()

    return mapping


def build_transcript(segments, mapping):
    """
    Convert WhisperX segments to a readable labeled transcript.
    Merges consecutive lines from the same speaker.
    """
    lines = []
    current_speaker = None
    current_block = []

    def flush_block():
        if current_block and current_speaker is not None:
            label = mapping.get(current_speaker, current_speaker)
            text = " ".join(current_block).strip()
            lines.append(f"{label}: {text}")

    for seg in segments:
        speaker = seg.get("speaker", UNKNOWN_LABEL)
        text = seg.get("text", "").strip()
        if not text:
            continue

        if speaker != current_speaker:
            flush_block()
            current_speaker = speaker
            current_block = [text]
        else:
            current_block.append(text)

    flush_block()
    return "\n\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Label WhisperX JSON speakers and produce a readable transcript."
    )
    parser.add_argument("input_json", help="Path to WhisperX JSON output file")
    parser.add_argument("output_txt", help="Path to write the labeled transcript")
    parser.add_argument(
        "--hosts",
        nargs="*",
        default=DEFAULT_HOSTS,
        metavar="NAME",
        help=f"Default host names to suggest (default: {' '.join(DEFAULT_HOSTS)})"
    )
    parser.add_argument(
        "--auto",
        action="store_true",
        help="Skip interactive prompts; assign speakers in order of first appearance"
    )
    args = parser.parse_args()

    if not os.path.isfile(args.input_json):
        print(f"ERROR: Input file not found: {args.input_json}")
        sys.exit(1)

    print(f"Loading: {args.input_json}")
    data = load_whisperx_json(args.input_json)

    segments = data.get("segments", [])
    if not segments:
        print("ERROR: No segments found in the JSON. Was diarization enabled?")
        sys.exit(1)

    # Check if any segment actually has a speaker field
    has_speaker = any("speaker" in seg for seg in segments)
    if not has_speaker:
        print("WARNING: No speaker labels found in segments.")
        print("         Make sure WhisperX was run with --diarize.")
        print("         Proceeding with all text as 'Unknown'.")

    samples = gather_speaker_samples(segments)

    if not samples or list(samples.keys()) == [UNKNOWN_LABEL]:
        print("No diarized speakers detected. Writing plain transcript.")
        lines = [seg.get("text", "").strip() for seg in segments if seg.get("text", "").strip()]
        transcript = "\n\n".join(lines)
    elif args.auto:
        # Auto mode: assign speakers in order of first appearance
        speaker_ids = sorted(
            samples.keys(),
            key=lambda sid: next(
                (i for i, seg in enumerate(segments) if seg.get("speaker") == sid),
                float("inf"),
            ),
        )
        mapping = {
            speaker_ids[i]: (args.hosts[i] if i < len(args.hosts) else "Unknown")
            for i in range(len(speaker_ids))
        }
        print()
        print("Auto speaker assignment (--auto mode):")
        for speaker_id, name in mapping.items():
            print(f"  {speaker_id} -> {name}")
        print()
        transcript = build_transcript(segments, mapping)
    else:
        mapping = prompt_speaker_labels(samples, args.hosts)
        transcript = build_transcript(segments, mapping)

    out_dir = os.path.dirname(args.output_txt)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    with open(args.output_txt, "w", encoding="utf-8") as f:
        f.write(transcript)
        f.write("\n")

    print(f"Transcript saved to: {args.output_txt}")


if __name__ == "__main__":
    main()
