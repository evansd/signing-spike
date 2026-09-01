#!/usr/bin/env python3
r"""
Pull, verify, and re-tag a container image to promote it to production

Example:
    ./pull_verify_retag.py \
      ghcr.io/evansd/signing-spike:production \
      --target-ref local/signing-spike:verified \
      --github-repo evansd/signing-spike \
      --branch main \
      --workflow-file .github/workflows/build-and-release.yml
"""

import argparse
import json
import subprocess
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent


def parse_args(argv):
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("image_ref", help="source Docker image reference")
    parser.add_argument(
        "--target-ref",
        required=True,
        help="tag to create after verification",
    )
    parser.add_argument(
        "--github-repo",
        required=True,
        help="GitHub repository expected in the signing certificate (OWNER/REPO)",
    )
    parser.add_argument(
        "--branch",
        required=True,
        help="source branch expected in the signing certificate",
    )
    parser.add_argument(
        "--workflow-file",
        required=True,
        help="workflow path expected in the signing certificate",
    )
    parser.add_argument(
        "--cosign-bin",
        type=Path,
        default=SCRIPT_DIR / "cosign",
        help="path to cosign binary (default: %(default)s)",
    )
    parser.add_argument(
        "--trust-root",
        type=Path,
        default=SCRIPT_DIR / "trusted_root.json",
        help="path to trusted_root.json (default: %(default)s)",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="only produce output on error or update",
    )

    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    log = print if not args.quiet else lambda _: None
    pull_verify_retag(**vars(args), log=log)


def pull_verify_retag(
    *,
    image_ref,
    target_ref,
    github_repo,
    branch,
    workflow_file,
    trust_root,
    cosign_bin,
    quiet,
    log=print,
):
    log(f"Running:\n  docker pull {image_ref}")
    run("docker", "pull", "--quiet", image_ref)

    image_id = get_image_id(image_ref)
    target_ref_id = get_image_id(target_ref, none_if_missing=True)
    if image_id == target_ref_id:
        log(f"Nothing to do; image IDs already match:\n  {image_ref}\n  {target_ref}")
        return

    image_digest = get_image_digest(image_ref, image_id)

    print(f"Verifying new image:\n  ID: {image_id}\n  Digest: {image_digest}")
    verify_image(
        cosign_bin=cosign_bin,
        trust_root=trust_root,
        image_digest=image_digest,
        github_repo=github_repo,
        branch=branch,
        workflow_file=workflow_file,
    )

    print(f"Image verified; updating local tag reference:\n  {target_ref}")
    run("docker", "tag", image_id, target_ref)


def run(*command):
    try:
        return subprocess.run(command, check=True, text=True, capture_output=True)
    except subprocess.CalledProcessError as exc:
        exc.add_note(f"\nstdout:\n{exc.stdout}\n\nstderr:\n{exc.stderr}")
        raise


def get_image_id(image_ref, none_if_missing=False):
    try:
        result = run("docker", "image", "inspect", "--format", "{{.Id}}", image_ref)
    except subprocess.CalledProcessError as exc:
        if none_if_missing and "No such image" in (exc.stderr or ""):
            return
        raise
    return result.stdout.strip()


def get_image_digest(image_ref, image_id):
    result = run(
        "docker", "image", "inspect", "--format", "{{json .RepoDigests}}", image_id
    )
    digests = json.loads(result.stdout)
    image_name = image_ref.rpartition(":")[0]
    matching_digests = [d for d in digests if d.startswith(f"{image_name}@")]
    assert len(matching_digests) == 1, (
        f"Expected exactly 1 match: {matching_digests!r} in {digests!r}"
    )
    return matching_digests[0]


def verify_image(
    *, cosign_bin, trust_root, image_digest, github_repo, branch, workflow_file
):
    git_ref = f"refs/heads/{branch}"
    identity = f"https://github.com/{github_repo}/{workflow_file}@{git_ref}"
    common = (
        "--trusted-root",
        trust_root,
        "--certificate-identity",
        identity,
        "--certificate-oidc-issuer",
        "https://token.actions.githubusercontent.com",
        "--certificate-github-workflow-repository",
        github_repo,
        "--certificate-github-workflow-ref",
        git_ref,
    )

    run(
        cosign_bin,
        "verify",
        *common,
        image_digest,
    )
    run(
        cosign_bin,
        "verify-attestation",
        "--type",
        "https://slsa.dev/provenance/v1",
        *common,
        image_digest,
    )


if __name__ == "__main__":
    main()
