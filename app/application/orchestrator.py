import time
import asyncio
from typing import Dict, List, Optional, Tuple, Type
from pydantic import BaseModel
from app.core.config import settings
from app.core.exceptions import LLMProviderError, JSONParseError
from app.domain.entities import JobStatus, ItemStatus, StageType, EventStatus, QuestionItem, JudgeRubric
from app.domain.interfaces import LLMProvider, JobRepository, ItemRepository, EventRepository
from app.providers.llm.openai import OpenAIProvider
from app.providers.llm.gemini import GeminiProvider

class PipelineOrchestrator:
    def __init__(
        self,
        job_repo: JobRepository,
        item_repo: ItemRepository,
        event_repo: EventRepository,
        primary_provider: LLMProvider,
        fallback_provider: LLMProvider
    ):
        self.job_repo = job_repo
        self.item_repo = item_repo
        self.event_repo = event_repo
        self.primary_provider = primary_provider
        self.fallback_provider = fallback_provider
        
        # Concurrency throttle
        self.semaphore = asyncio.Semaphore(settings.MAX_CONCURRENT_LLM_CALLS)
        
        # Circuit breaker state
        self.consecutive_failures = 0
        self.circuit_open = False
        self.circuit_cooldown_until = 0.0

    def _load_prompt(self, filename: str) -> str:
        from app.core.config import BASE_DIR
        path = BASE_DIR / "prompts" / filename
        with open(path, "r") as f:
            return f.read()

    def _get_active_provider(self) -> LLMProvider:
        """Returns the active provider based on circuit breaker state."""
        if self.circuit_open:
            if time.time() > self.circuit_cooldown_until:
                # Cooldown expired, reset circuit
                self.circuit_open = False
                self.consecutive_failures = 0
                return self.primary_provider
            else:
                return self.fallback_provider
        return self.primary_provider

    def _report_provider_success(self):
        if not self.circuit_open:
            self.consecutive_failures = 0

    def _report_provider_failure(self):
        if not self.circuit_open:
            self.consecutive_failures += 1
            if self.consecutive_failures >= 3:
                # Trip circuit breaker for 60 seconds
                self.circuit_open = True
                self.circuit_cooldown_until = time.time() + 60.0

    async def _call_llm_with_fallback(
        self, 
        system_prompt: str, 
        user_prompt: str, 
        response_model: Type[BaseModel]
    ) -> Tuple[BaseModel, Dict[str, any]]:
        """Handles provider execution with circuit-breaking fallback logic."""
        async with self.semaphore:
            provider = self._get_active_provider()
            try:
                result, metadata = await provider.generate_structured_output(
                    system_prompt, user_prompt, response_model, settings.LLM_TEMPERATURE
                )
                self._report_provider_success()
                return result, metadata
            except Exception as e:
                self._report_provider_failure()
                
                # If using primary and it failed, try immediate fallback to alternative provider
                if provider == self.primary_provider:
                    fallback_provider = self.fallback_provider
                    try:
                        result, metadata = await fallback_provider.generate_structured_output(
                            system_prompt, user_prompt, response_model, settings.LLM_TEMPERATURE
                        )
                        return result, metadata
                    except Exception as fallback_err:
                        raise LLMProviderError(f"Both primary and fallback providers failed. Primary: {str(e)}. Fallback: {str(fallback_err)}")
                raise e

    def _perform_rule_validation(self, item: QuestionItem) -> Tuple[bool, str]:
        """Performs static rule-based validation checking structural rules."""
        # 1. Exactly 4 choices
        if not item.choices or len(item.choices) != 4:
            return False, f"Rule Error: Choices must contain exactly 4 choices. Found {len(item.choices) if item.choices else 0}."
        
        # 2. Choice keys must be exactly A, B, C, D
        expected_keys = {"A", "B", "C", "D"}
        actual_keys = set(item.choices.keys())
        if actual_keys != expected_keys:
            return False, f"Rule Error: Choice keys must be exactly A, B, C, D. Found {actual_keys}."

        # 3. All choice values must be unique
        choice_values = list(item.choices.values())
        if len(set(choice_values)) != len(choice_values):
            return False, "Rule Error: All choice text values must be unique to prevent duplicates."

        # 4. Correct answer reference checks
        if item.correct_answer not in expected_keys:
            return False, f"Rule Error: Correct answer must be A, B, C, or D. Found '{item.correct_answer}'."

        # 5. Non-empty fields
        if not item.question.strip():
            return False, "Rule Error: Question text cannot be empty."
        if not item.explanation.strip():
            return False, "Rule Error: Explanation cannot be empty."

        return True, "Rules passed"

    async def execute_job(self, job_id: str) -> None:
        """Runs the generation job through the multi-agent queue."""
        job = await self.job_repo.get_by_id(job_id)
        if not job:
            return

        await self.job_repo.update_status(job_id, JobStatus.PROCESSING)
        
        subject = job["subject"]
        difficulty = job["difficulty"]
        items_requested = job["items_requested"]
        
        # Load prompt templates
        generator_template = self._load_prompt("generator_v1.txt")
        judge_template = self._load_prompt("judge_v1.txt")
        repair_template = self._load_prompt("repair_v1.txt")

        # Read count of already generated items (durable crash recovery checkpoint)
        completed_items = await self.item_repo.get_items_by_job_id(job_id)
        items_validated_count = sum(1 for it in completed_items if it["status"] == ItemStatus.VALIDATED)
        items_needed = items_requested - items_validated_count

        total_cost = sum(it["cost"] for it in completed_items)
        start_time = time.time()

        try:
            for i in range(items_needed):
                # Update job heartbeat after starting a new item cycle
                await self.job_repo.update_heartbeat(job_id)
                
                # 1. Generation Stage
                gen_sys = generator_template.format(subject=subject, difficulty=difficulty)
                gen_usr = f"Generate 1 MCQ about {subject} at {difficulty} level."
                
                gen_start = time.time()
                try:
                    generated_mcq, gen_meta = await self._call_llm_with_fallback(
                        gen_sys, gen_usr, QuestionItem
                    )
                    gen_duration = int((time.time() - gen_start) * 1000)
                    await self.event_repo.log_event(
                        job_id=job_id,
                        stage=StageType.GENERATION.value,
                        status=EventStatus.SUCCESS.value,
                        duration_ms=gen_duration,
                        input_tokens=gen_meta["input_tokens"],
                        output_tokens=gen_meta["output_tokens"],
                        cost=gen_meta["cost"],
                        model=gen_meta["model"]
                    )
                except Exception as e:
                    gen_duration = int((time.time() - gen_start) * 1000)
                    await self.event_repo.log_event(
                        job_id=job_id,
                        stage=StageType.GENERATION.value,
                        status=EventStatus.FAILURE.value,
                        duration_ms=gen_duration,
                        input_tokens=0,
                        output_tokens=0,
                        cost=0.0,
                        model="unknown",
                        error_message=str(e)
                    )
                    raise e

                # 2. Validation Stage (Static Rules + LLM Judge)
                rule_pass, rule_feedback = self._perform_rule_validation(generated_mcq)
                
                judge_rubric = None
                val_meta = {"cost": 0.0, "input_tokens": 0, "output_tokens": 0, "model": settings.JUDGE_MODEL}
                
                if rule_pass:
                    # Run LLM Judge
                    judge_sys = judge_template.format(
                        subject=subject,
                        difficulty=difficulty,
                        question=generated_mcq.question,
                        choices=str(generated_mcq.choices),
                        correct_answer=generated_mcq.correct_answer,
                        explanation=generated_mcq.explanation
                    )
                    judge_usr = "Evaluate the generated MCQ question."
                    
                    val_start = time.time()
                    try:
                        judge_rubric, val_meta = await self._call_llm_with_fallback(
                            judge_sys, judge_usr, JudgeRubric
                        )
                        val_duration = int((time.time() - val_start) * 1000)
                        await self.event_repo.log_event(
                            job_id=job_id,
                            stage=StageType.VALIDATION.value,
                            status=EventStatus.SUCCESS.value,
                            duration_ms=val_duration,
                            input_tokens=val_meta["input_tokens"],
                            output_tokens=val_meta["output_tokens"],
                            cost=val_meta["cost"],
                            model=val_meta["model"]
                        )
                    except Exception as e:
                        val_duration = int((time.time() - val_start) * 1000)
                        await self.event_repo.log_event(
                            job_id=job_id,
                            stage=StageType.VALIDATION.value,
                            status=EventStatus.FAILURE.value,
                            duration_ms=val_duration,
                            input_tokens=0,
                            output_tokens=0,
                            cost=0.0,
                            model="unknown",
                            error_message=str(e)
                        )
                        raise e
                else:
                    # Construct mock failed rubric for rule failure
                    judge_rubric = JudgeRubric(
                        schema_valid=False,
                        difficulty_alignment=0.0,
                        factuality_score=0.0,
                        clarity_score=0.0,
                        explanation_alignment=False,
                        overall_passed=False,
                        feedback=rule_feedback
                    )

                # Persist the item in database (State: VALIDATING if passed, else REPAIRING)
                initial_cost = gen_meta["cost"] + val_meta["cost"]
                total_cost += initial_cost
                
                item_status = ItemStatus.VALIDATED if judge_rubric.overall_passed else ItemStatus.REPAIRING
                
                item_record = await self.item_repo.create(
                    job_id=job_id,
                    question=generated_mcq.question,
                    choices=generated_mcq.choices,
                    correct_answer=generated_mcq.correct_answer,
                    explanation=generated_mcq.explanation,
                    cost=initial_cost,
                    status=item_status,
                    attempts=1
                )
                
                item_id = item_record["id"]
                attempts = 1

                # 3. Repair Agent Stage (if validation failed)
                while item_status == ItemStatus.REPAIRING and attempts <= settings.MAX_REPAIR_ATTEMPTS:
                    await self.job_repo.update_heartbeat(job_id)
                    attempts += 1
                    
                    repair_sys = repair_template.format(
                        subject=subject,
                        difficulty=difficulty,
                        question=generated_mcq.question,
                        choices=str(generated_mcq.choices),
                        correct_answer=generated_mcq.correct_answer,
                        explanation=generated_mcq.explanation,
                        feedback=judge_rubric.feedback
                    )
                    repair_usr = "Correct the question according to auditor feedback."
                    
                    rep_start = time.time()
                    try:
                        repaired_mcq, rep_meta = await self._call_llm_with_fallback(
                            repair_sys, repair_usr, QuestionItem
                        )
                        rep_duration = int((time.time() - rep_start) * 1000)
                        await self.event_repo.log_event(
                            job_id=job_id,
                            stage=StageType.REPAIR.value,
                            status=EventStatus.SUCCESS.value,
                            duration_ms=rep_duration,
                            input_tokens=rep_meta["input_tokens"],
                            output_tokens=rep_meta["output_tokens"],
                            cost=rep_meta["cost"],
                            model=rep_meta["model"]
                        )
                        
                        total_cost += rep_meta["cost"]
                        # Update item database content to reflect repair attempt
                        await self.item_repo.update_item_content(
                            item_id=item_id,
                            question=repaired_mcq.question,
                            choices=repaired_mcq.choices,
                            correct_answer=repaired_mcq.correct_answer,
                            explanation=repaired_mcq.explanation,
                            status=ItemStatus.VALIDATING,
                            attempts=attempts,
                            cost_increment=rep_meta["cost"]
                        )
                        
                        # Re-run Quality validation on repaired item
                        rule_pass, rule_feedback = self._perform_rule_validation(repaired_mcq)
                        if rule_pass:
                            judge_sys = judge_template.format(
                                subject=subject,
                                difficulty=difficulty,
                                question=repaired_mcq.question,
                                choices=str(repaired_mcq.choices),
                                correct_answer=repaired_mcq.correct_answer,
                                explanation=repaired_mcq.explanation
                            )
                            val_start = time.time()
                            judge_rubric, val_meta = await self._call_llm_with_fallback(
                                judge_sys, judge_usr, JudgeRubric
                            )
                            val_duration = int((time.time() - val_start) * 1000)
                            await self.event_repo.log_event(
                                job_id=job_id,
                                stage=StageType.VALIDATION.value,
                                status=EventStatus.SUCCESS.value,
                                duration_ms=val_duration,
                                input_tokens=val_meta["input_tokens"],
                                output_tokens=val_meta["output_tokens"],
                                cost=val_meta["cost"],
                                model=val_meta["model"]
                            )
                            total_cost += val_meta["cost"]
                            await self.item_repo.update_status_and_attempts(
                                item_id=item_id,
                                status=ItemStatus.VALIDATING,
                                attempts=attempts,
                                cost_increment=val_meta["cost"]
                            )
                        else:
                            judge_rubric = JudgeRubric(
                                schema_valid=False,
                                difficulty_alignment=0.0,
                                factuality_score=0.0,
                                clarity_score=0.0,
                                explanation_alignment=False,
                                overall_passed=False,
                                feedback=rule_feedback
                            )
                        
                        # Update status based on re-evaluation
                        if judge_rubric.overall_passed:
                            item_status = ItemStatus.VALIDATED
                        else:
                            item_status = ItemStatus.REPAIRING
                            
                        # Save latest generated for subsequent iterations
                        generated_mcq = repaired_mcq
                        
                    except Exception as e:
                        rep_duration = int((time.time() - rep_start) * 1000)
                        await self.event_repo.log_event(
                            job_id=job_id,
                            stage=StageType.REPAIR.value,
                            status=EventStatus.FAILURE.value,
                            duration_ms=rep_duration,
                            input_tokens=0,
                            output_tokens=0,
                            cost=0.0,
                            model="unknown",
                            error_message=str(e)
                        )
                        raise e

                # Check if item finally passed or requires review
                if item_status == ItemStatus.VALIDATED:
                    await self.item_repo.update_status_and_attempts(
                        item_id=item_id,
                        status=ItemStatus.VALIDATED,
                        attempts=attempts
                    )
                else:
                    # Bounded retries exhausted -> Move to REQUIRES_REVIEW (HITL state)
                    await self.item_repo.update_status_and_attempts(
                        item_id=item_id,
                        status=ItemStatus.REQUIRES_REVIEW,
                        attempts=attempts
                    )
            
            # Job finished successfully
            await self.job_repo.update_status(job_id, JobStatus.COMPLETED)
            
        except Exception as e:
            # Job failed
            await self.job_repo.update_status(job_id, JobStatus.FAILED, error_message=str(e))
        
        # Update metrics (total cost and duration)
        duration = time.time() - start_time
        await self.job_repo.update_metrics(job_id, total_cost, duration)
