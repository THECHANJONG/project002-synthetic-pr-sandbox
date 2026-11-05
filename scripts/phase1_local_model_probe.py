"""Isolated public-sandbox proof: real pinned local model generates a code candidate.

No remote code writes, PR creation, merge, or execution of generated source.
A success is a model-inference proof only, NOT autonomous developer E2E.
"""
import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import re

REPOSITORY = "THECHANJONG/project002-synthetic-pr-sandbox"
BRANCH = "refs/heads/foundation/phase1-local-model-proof-20261106"
MODEL_ID = "Qwen/Qwen2.5-Coder-0.5B-Instruct"
MODEL_REVISION = "ea3f2471cf1b1f0db85067f1ef93848e38e88c25"
SHA = re.compile(r"[0-9a-f]{40}\Z")
PROMPT = (
    "Return Python source code only, with no Markdown, comments, imports, "
    "or explanation. Define one function named add_numbers with exactly two "
    "parameters named left and right, which returns left + right."
)


class ProbeBlocked(ValueError):
    pass


def validate_environment(env):
    if env.get("GITHUB_REPOSITORY") != REPOSITORY or env.get("GITHUB_REF") != BRANCH:
        raise ProbeBlocked("wrong repository or branch")
    head = env.get("EXPECTED_HEAD")
    if type(head) is not str or not SHA.fullmatch(head):
        raise ProbeBlocked("missing exact HEAD")
    if env.get("CHECKED_OUT_HEAD") != head:
        raise ProbeBlocked("checkout SHA mismatch")
    if env.get("GITHUB_EVENT_NAME") != "push":
        raise ProbeBlocked("unsupported event")
    if not re.fullmatch(r"[1-9][0-9]*", env.get("GITHUB_RUN_ID", "")):
        raise ProbeBlocked("invalid Actions run ID")
    return head


def normalize_candidate(raw):
    """Parse and inspect model output statically. Never import or execute it."""
    if type(raw) is not str or not raw.strip() or len(raw.encode("utf-8")) > 4096:
        raise ProbeBlocked("missing or oversized generated output")
    candidate = raw.strip()
    fence = chr(96) * 3
    if candidate.startswith(fence) and candidate.endswith(fence):
        lines = candidate.splitlines()
        if len(lines) >= 3 and lines[0] in (fence, fence + "python") and lines[-1] == fence:
            candidate = "\n".join(lines[1:-1]).strip()
    try:
        tree = ast.parse(candidate, mode="exec")
    except (SyntaxError, ValueError, RecursionError) as exc:
        raise ProbeBlocked("generated Python syntax invalid") from exc
    if len(tree.body) != 1 or type(tree.body[0]) is not ast.FunctionDef:
        raise ProbeBlocked("model must produce one function only")
    fn = tree.body[0]
    if fn.name != "add_numbers" or fn.decorator_list or getattr(fn, "type_params", []):
        raise ProbeBlocked("wrong function identity")
    args = fn.args
    if (len(args.args) != 2 or [a.arg for a in args.args] != ["left", "right"]
            or args.posonlyargs or args.kwonlyargs or args.defaults or args.kw_defaults
            or args.vararg is not None or args.kwarg is not None):
        raise ProbeBlocked("wrong function parameters")
    if len(fn.body) != 1 or type(fn.body[0]) is not ast.Return:
        raise ProbeBlocked("unexpected generated statements")
    value = fn.body[0].value
    if not (type(value) is ast.BinOp and type(value.op) is ast.Add
            and type(value.left) is ast.Name and value.left.id == "left"
            and type(value.right) is ast.Name and value.right.id == "right"):
        raise ProbeBlocked("wrong generated behavior")
    return candidate + "\n"


def run_probe(env, output_dir, inference):
    head = validate_environment(env)
    target = Path(output_dir)
    if target.exists():
        raise ProbeBlocked("output directory already exists")
    generated, observed = inference(PROMPT)
    if (type(observed) is not dict or observed.get("model_revision") != MODEL_REVISION
            or observed.get("model_loaded_and_generated") is not True
            or type(observed.get("generated_token_count")) is not int
            or observed["generated_token_count"] <= 0):
        raise ProbeBlocked("actual inference not observed")
    code = normalize_candidate(generated)
    receipt = {
        "proof_scope": "LOCAL_MODEL_GENERATION_STATIC_CHECK_ONLY",
        "repository": REPOSITORY,
        "head_sha": head,
        "actions_run_id": int(env["GITHUB_RUN_ID"]),
        "model_id": MODEL_ID,
        "model_revision": MODEL_REVISION,
        "prompt_sha256": hashlib.sha256(PROMPT.encode()).hexdigest(),
        "candidate_sha256": hashlib.sha256(code.encode()).hexdigest(),
        "candidate_bytes": len(code.encode()),
        "generated_tokens": observed["generated_token_count"],
        "github_writes": False,
        "pr_created": False,
        "merged": False,
        "scheduler_invocation_attestation": "UNAVAILABLE",
        "autonomous_development_e2e": "NOT_PROVEN",
    }
    target.mkdir(parents=True)
    (target / "candidate.py").write_text(code, encoding="utf-8")
    (target / "receipt.json").write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    return receipt


def local_inference(prompt):
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    torch.set_num_threads(2)
    tokenizer = AutoTokenizer.from_pretrained(MODEL_ID, revision=MODEL_REVISION,
                                               trust_remote_code=False)
    model = AutoModelForCausalLM.from_pretrained(
        MODEL_ID, revision=MODEL_REVISION, torch_dtype=torch.float32,
        trust_remote_code=False,
    )
    model.eval()
    messages = [{"role": "system", "content": "Return valid Python code only."},
                {"role": "user", "content": prompt}]
    inputs = tokenizer.apply_chat_template(messages, add_generation_prompt=True,
                                           return_tensors="pt")
    with torch.inference_mode():
        output = model.generate(inputs, do_sample=False, max_new_tokens=96,
                                pad_token_id=tokenizer.eos_token_id)
    tokens = output[0][inputs.shape[-1]:]
    return tokenizer.decode(tokens, skip_special_tokens=True), {
        "model_revision": MODEL_REVISION,
        "model_loaded_and_generated": True,
        "generated_token_count": int(tokens.shape[0]),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()
    try:
        receipt = run_probe(os.environ, args.output_dir, local_inference)
    except ProbeBlocked as exc:
        print(json.dumps({"status": "FAIL_CLOSED", "reason": str(exc)}))
        return 3
    print("LOCAL_MODEL_CODE_GENERATED=" + json.dumps(receipt, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
