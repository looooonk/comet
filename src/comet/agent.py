"""Bounded corrections from ordinary execution observations, without scoring."""


def execution_feedback(observation: str, streak: int, limit: int) -> tuple[int, str]:
    if not observation.startswith(("Execution failed", "Invalid action:")):
        return 0, ""
    streak += 1
    if observation.startswith("Invalid action:"):
        guidance = (
            "Close any reasoning block and return one short executable Python block. "
            "If information is missing, make one printed documentation or inspection query. "
            "Comments and hypothetical code do not perform the task."
        )
    elif "Response status code is 401" in observation or "HTTP 401" in observation:
        guidance = (
            "Read the login signature, call login with the app password, and save the returned "
            "access_token. Pass that token to endpoints that require it. Retrieving a password "
            "or describing login in comments does not authenticate later calls."
        )
    elif any(name in observation for name in ("TypeError", "KeyError", "AttributeError")):
        guidance = (
            "Inspect the actual object's type, keys, or a small sample before rewriting the "
            "larger action. Use returned objects instead of invented placeholders."
        )
    else:
        guidance = "Read the exact API signature and correct the observed error before retrying."
    return streak, (
        f"Consecutive execution/action failures: {streak}/{limit}. {guidance} "
        "Do not repeat the unchanged failing block. Earlier actions in that block may already "
        "have taken effect. This attempt ends at the configured failure limit."
    )
