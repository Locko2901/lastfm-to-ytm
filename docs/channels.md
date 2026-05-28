# Release Channels

!!! tip "Which one should I pick?"
    **Stay on `stable` unless you have a reason not to.** Stable = tagged releases (`vX.Y.Z`), upgraded only when you choose. Dev = the latest commit on `main`, useful if you want bleeding-edge fixes or are testing in-progress work. You can switch freely - nothing is destructive.

The dashboard's version pill tells you which **update channel** you're on and lights up when there's something new:

- **stable** - you're running a tagged release (`vX.Y.Z`). The pill lights up when a newer release is published. Recommended for most people.
- **dev** - you're running the latest in-progress code from the `main` branch. The pill lights up whenever a new commit lands.

This applies equally to Docker (prebuilt and local-build) and standalone CLI installs - there's no persistent flag, the channel is inferred from what you're actually running.

## How the channel is decided

| How you start the app | You get **stable** when&hellip; | You get **dev** when&hellip; |
|---|---|---|
| Prebuilt Docker (`./run-docker.sh --pull[=TAG]`) | `--pull`, `--pull=latest`, or `--pull=vX.Y.Z` | `--pull=dev` or `--pull=main` |
| Local Docker build (`./run-docker.sh` after `git clone`) | You ran `git checkout vX.Y.Z` (a specific release) | Anything else - including a fresh `git clone` that lands on `main` |
| Standalone Python (`python run.py`) | You ran `git checkout vX.Y.Z` | Anything else |

For the two Docker paths, `run-docker.sh` writes the answer to a tiny `.channel` file in the project root (right next to `COMMIT_SHA`) and the dashboard reads it. For standalone, the dashboard asks `git` directly.

!!! warning "Why `git clone` is always **dev**, even right after a release"
    A fresh `git clone` (or `git checkout main`) leaves you on the `main` *branch*, even if the latest commit on `main` happens to be a release commit. That's intentional - the next commit will be a dev commit. To be on **stable**, you have to explicitly check out a release tag (e.g. `git checkout v1.2.3`).

## Switching channels

"Switching" just means running the install path for the other channel.

=== "Docker (prebuilt)"

    ```bash
    # Move to dev
    ./run-docker.sh --pull=dev

    # Back to stable
    ./run-docker.sh --pull            # or --pull=vX.Y.Z to pin
    ```

=== "Docker (local build)"

    ```bash
    # Move to dev
    git checkout main && ./run-docker.sh --rebuild

    # Move to stable
    git fetch --tags
    git checkout "$(git tag --sort=-v:refname | head -1)"
    ./run-docker.sh --rebuild
    ```

=== "Standalone CLI"

    Either change your checkout (`git checkout <tag-or-main>`) or force the channel via env var - it overrides git-state detection:

    ```bash
    export YTMT_CHANNEL=dev      # or stable
    ```

    Persist it by adding the line to your shell profile, `.env`, or the systemd unit's `Environment=` directive.

For Docker, the one-shot `--channel=stable|dev` flag is available too if you want to override detection for a single invocation without changing the actual build.

## Forcing a channel

Set `YTMT_CHANNEL=stable` (or `dev`) in your environment to override detection, or pass `--channel=stable|dev` to `run-docker.sh` for a one-shot override.

---

See [Updating](docker-reference.md#updating) for the per-install upgrade commands, or [Releases &amp; Changelog](releases.md) for the maintainer-side view of how release tags get produced.
