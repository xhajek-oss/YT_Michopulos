from matching.tv_matcher import TVMatcher


def main() -> None:
    matcher = TVMatcher()
    matches = matcher.find_candidates(min_score=50)
    print(f"[MATCH] candidates={len(matches)}")
    for item in matches:
        print(
            f"[MATCH] event_id={item.sports_event_id} tv_id={item.tv_program_id} "
            f"score={item.score} status={item.status} reasons={','.join(item.reasons)}"
        )


if __name__ == "__main__":
    main()
