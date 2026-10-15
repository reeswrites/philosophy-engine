"""Stage: reconstruct. Argument row -> ReconstructionX via LLM, stored with source='llm'."""
from __future__ import annotations

from . import config, prompts
from .models_ext import ReconstructionX
from .runner import Ctx, Unit, register
from .stage_common import feedback, opt, validation_errors


@register("reconstruct")
def reconstruct(ctx: Ctx, unit: Unit) -> None:
    a = ctx.store.get_argument(unit.argument_id)
    # (not load_split: its own `name` parameter collides with the {{ name }} template variable)
    system, user = prompts.split(prompts.render(
        prompts.load("reconstruct", "v1"), name=a.get("name", ""), author=a.get("author", ""),
        work=a.get("work", ""), source_text=a.get("source_text", "")))
    schema = ReconstructionX.model_json_schema()
    model = opt(ctx, "model_reason", None)
    temp = opt(ctx, "temperature_reconstruct", config.TEMP_RECONSTRUCT)
    rec, errs, res = None, [], None
    for attempt in range(2):
        u = user if attempt == 0 else user + "\n\n" + feedback(errs)
        res = ctx.llm.call(stage="reconstruct", system=system, user=u, schema=schema,
                           argument_id=unit.argument_id, sample_idx=0, temperature=temp,
                           model=model, prompt_name="reconstruct.v1")
        rec, errs = validation_errors(ReconstructionX, res.data)
        if rec is not None and len(rec.premises) == 0:
            rec, errs = None, ["reconstruction has no premises"]
        if rec is not None:
            break
    if rec is None:
        raise ValueError(f"reconstruct {unit.argument_id}: unparseable after retry: {errs}")
    ctx.store.insert_reconstruction(unit.argument_id, "llm", rec, model=res.model,
                                    run_id=ctx.run_id, llm_call_id=res.call_id)
