"""Session offering search and one-course replacement.

These two routes call the existing Java tools ``listOfferings`` and
``validatePlan``. Both paths are in ``planning.openapi.json``.

A missing Java service stays ``503 TOOL_UNAVAILABLE``. A saved plan with no
offering snapshot never calls Java: search answers ``200`` with envelope
``UNKNOWN`` and empty ``items`` (the page must not read that as "no classes").
Replace still does not invent a ``PlanValidation``. The returned
``verification`` is Java's object, including ``INVALID`` and ``UNKNOWN``.
"""

from __future__ import annotations

import json
from typing import Annotated, Any, cast

from fastapi import APIRouter, Depends, Header, Query, Request

from agent_runtime.api.deps import (
    get_idempotency,
    get_plan_store,
    get_tool_client,
    make_context,
    require_subject,
)
from agent_runtime.api.errors import InvalidInputError, NotFoundError, envelope
from agent_runtime.api.idempotency import IdempotencyStore
from agent_runtime.api.schemas import DomainModel, Issue
from agent_runtime.api.schemas._base import Id
from agent_runtime.application.ids import digest
from agent_runtime.application.plan_replacement import (
    CourseNotInPlan,
    OfferingSnapshotMissing,
    PlanNotInSession,
    PlanReplacement,
    ReplacementResult,
    ReusedVerification,
    UnknownClass,
)
from agent_runtime.application.plan_store import SessionPlanStore

router = APIRouter()


class ReplacePlanBody(DomainModel):
    previousPlanId: Id
    courseCode: Id
    selectedClassId: Id


class OfferingQuery(DomainModel):
    previousPlanId: Id
    courseCode: Id


def _reject(error: Exception) -> None:
    if isinstance(error, PlanNotInSession):
        raise NotFoundError("方案不在当前会话") from error
    if isinstance(error, UnknownClass):
        raise NotFoundError("班次不在这门课的当前查询结果里", field="selectedClassId") from error
    if isinstance(error, CourseNotInPlan):
        raise InvalidInputError(str(error), field="courseCode") from error
    if isinstance(error, OfferingSnapshotMissing):
        # Replace cannot return an empty offering list: its contract requires a
        # Java PlanValidation, and this module does not write one. The field is
        # omitted because the client never sent offeringSnapshotId.
        raise InvalidInputError(
            "这份方案没有班次快照，不能替换班次",
        ) from error
    if isinstance(error, ReusedVerification):
        raise InvalidInputError(
            "核验结果复用了旧判决编号，已拒绝",
            field="verifierResultId",
            code="VERIFICATION_REUSED",
        ) from error
    raise error


def _replacement_payload(result: ReplacementResult) -> dict:
    return {
        "previousPlanId": result.previous_plan_id,
        "planId": result.plan_id,
        "items": [item.model_dump(mode="json") for item in result.items],
        "hardConstraints": [item.model_dump(mode="json") for item in result.hard_constraints],
        "verification": result.verification.model_dump(mode="json"),
    }


@router.get("/api/v1/session-offerings")
def search_session_offerings(
    request: Request,
    subject_id: Annotated[str, Depends(require_subject)],
    x_request_id: Annotated[str, Header(alias="X-Request-Id")],
    previous_plan_id: Annotated[str, Query(alias="previousPlanId", min_length=1, max_length=120)],
    course_code: Annotated[str, Query(alias="courseCode", min_length=1, max_length=120)],
    plans: Annotated[SessionPlanStore, Depends(get_plan_store)],
    tool_client: Annotated[Any, Depends(get_tool_client)],
) -> dict:
    query = OfferingQuery(previousPlanId=previous_plan_id, courseCode=course_code)
    context = make_context(request, subject_id, x_request_id)
    service = PlanReplacement(plans, cast(Any, tool_client))
    try:
        offerings = service.search(
            session_id=subject_id,
            previous_plan_id=query.previousPlanId,
            course_code=query.courseCode,
            context=context,
        )
    except OfferingSnapshotMissing:
        # The missing id is on the stored plan, not in this query. 200 UNKNOWN
        # with empty items matches the page: it must not say the course has no classes.
        return envelope(
            x_request_id,
            "UNKNOWN",
            {
                "previousPlanId": query.previousPlanId,
                "courseCode": query.courseCode,
                "items": [],
            },
            issues=[
                Issue(
                    code="OFFERING_SNAPSHOT_MISSING",
                    message="这份方案没有班次快照，不能确认有哪些班次",
                    field=None,
                    retryable=False,
                )
            ],
        ).model_dump(mode="json")
    except PlanNotInSession as exc:
        _reject(exc)
        raise
    return envelope(
        x_request_id,
        "OK",
        {
            "previousPlanId": query.previousPlanId,
            "courseCode": query.courseCode,
            "items": [item.model_dump(mode="json") for item in offerings],
        },
    ).model_dump(mode="json")


@router.post("/api/v1/session-plans/replace")
def replace_session_plan(
    request: Request,
    body: ReplacePlanBody,
    subject_id: Annotated[str, Depends(require_subject)],
    x_request_id: Annotated[str, Header(alias="X-Request-Id")],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
    plans: Annotated[SessionPlanStore, Depends(get_plan_store)],
    idempotency: Annotated[IdempotencyStore, Depends(get_idempotency)],
    tool_client: Annotated[Any, Depends(get_tool_client)],
) -> dict:
    body_digest = digest(
        json.dumps(body.model_dump(mode="json"), sort_keys=True, ensure_ascii=False)
    )

    def produce() -> dict:
        context = make_context(request, subject_id, x_request_id)
        service = PlanReplacement(plans, cast(Any, tool_client))
        try:
            result = service.replace(
                session_id=subject_id,
                previous_plan_id=body.previousPlanId,
                course_code=body.courseCode,
                selected_class_id=body.selectedClassId,
                context=context,
            )
        except (
            PlanNotInSession,
            UnknownClass,
            CourseNotInPlan,
            OfferingSnapshotMissing,
            ReusedVerification,
        ) as exc:
            _reject(exc)
            raise
        return envelope(x_request_id, "OK", _replacement_payload(result)).model_dump(mode="json")

    return idempotency.run(
        subject_id, "session-plan-replace", idempotency_key, body_digest, produce
    )
