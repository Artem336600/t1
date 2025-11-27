"""
Interview Service - HR Bot for conducting interviews
Manages interview flow, integrates with AI for questions and Live Coding
"""
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
import os
import json
import uuid
import asyncio
from datetime import datetime
from enum import Enum

from interview_engine import InterviewEngine, InterviewSession
from ai_judge import AIJudge
from schema_parser import InterviewSchemaParser, InterviewStep

app = FastAPI(
    title="Interview Service",
    description="HR Bot for conducting technical interviews",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Store active interview sessions
active_sessions: Dict[str, InterviewSession] = {}

# Initialize engines
interview_engine = InterviewEngine()
ai_judge = AIJudge()


class InterviewSchemaRequest(BaseModel):
    """Request to start interview with schema"""
    nodes: List[Dict[str, Any]]
    edges: List[Dict[str, Any]]
    candidate_name: Optional[str] = "Кандидат"


class MessageRequest(BaseModel):
    """Chat message from candidate"""
    session_id: str
    message: str


class CodeSubmissionRequest(BaseModel):
    """Code submission for Live Coding"""
    session_id: str
    code: str
    language: str = "python"


class InterviewResult(BaseModel):
    """Final interview result"""
    session_id: str
    total_score: int
    max_score: int
    score_percent: float
    passed: bool
    sections: List[Dict[str, Any]]
    main_errors: List[str]
    recommendations: List[str]


@app.get("/health")
async def health():
    return {"status": "ok", "service": "interview-service"}


@app.post("/interview/start")
async def start_interview(request: InterviewSchemaRequest):
    """
    Start new interview session from schema.
    
    Parses the interview schema (nodes/edges) and creates a session.
    Returns session_id and first step.
    """
    try:
        # Parse schema
        parser = InterviewSchemaParser()
        steps = parser.parse(request.nodes, request.edges)
        
        if not steps:
            raise HTTPException(status_code=400, detail="No valid steps in schema")
        
        # Create session
        session_id = str(uuid.uuid4())
        session = InterviewSession(
            session_id=session_id,
            candidate_name=request.candidate_name,
            steps=steps,
            current_step_index=0,
            scores={},
            history=[],
            started_at=datetime.now(),
            current_level="junior"  # Start with junior level for live coding
        )
        
        active_sessions[session_id] = session
        
        # Get first step and generate greeting
        first_step = steps[0]
        greeting = await interview_engine.generate_greeting(session, first_step)
        
        session.history.append({
            "role": "assistant",
            "content": greeting,
            "step_id": first_step.id,
            "timestamp": datetime.now().isoformat()
        })
        
        return {
            "session_id": session_id,
            "message": greeting,
            "current_step": first_step.to_dict(),
            "total_steps": len(steps),
            "is_live_coding": first_step.node_type == "skill-group" and first_step.group_name == "Live Coding"
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/interview/start/stream")
async def start_interview_stream(request: InterviewSchemaRequest):
    """
    Start new interview session with streaming greeting.
    Returns SSE for real-time greeting display.
    """
    async def generate():
        try:
            # Parse schema
            parser = InterviewSchemaParser()
            steps = parser.parse(request.nodes, request.edges)
            
            if not steps:
                yield f"data: {json.dumps({'type': 'error', 'error': 'No valid steps in schema'})}\n\n"
                return
            
            # Create session
            session_id = str(uuid.uuid4())
            session = InterviewSession(
                session_id=session_id,
                candidate_name=request.candidate_name,
                steps=steps,
                current_step_index=0,
                scores={},
                history=[],
                started_at=datetime.now(),
                current_level="junior"
            )
            
            active_sessions[session_id] = session
            
            first_step = steps[0]
            
            # Send session info first
            yield f"data: {json.dumps({'type': 'session', 'session_id': session_id, 'current_step': first_step.to_dict(), 'total_steps': len(steps)})}\n\n"
            
            # Stream greeting
            full_greeting = ""
            async for chunk in interview_engine.generate_greeting_stream(session, first_step):
                full_greeting += chunk
                yield f"data: {json.dumps({'type': 'chunk', 'content': chunk})}\n\n"
            
            # Save greeting to history
            session.history.append({
                "role": "assistant",
                "content": full_greeting,
                "step_id": first_step.id,
                "timestamp": datetime.now().isoformat()
            })
            
            # Send done
            yield f"data: {json.dumps({'type': 'done', 'is_live_coding': first_step.node_type == 'skill-group' and first_step.group_name == 'Live Coding'})}\n\n"
            
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'error': str(e)})}\n\n"
    
    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


@app.post("/interview/message")
async def send_message(request: MessageRequest):
    """
    Send message to HR bot and get response.
    
    The bot will:
    1. Process the candidate's answer
    2. Evaluate it using AI Judge
    3. Decide if step is complete
    4. Move to next step if needed
    """
    session = active_sessions.get(request.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    try:
        # Add candidate message to history
        session.history.append({
            "role": "user",
            "content": request.message,
            "timestamp": datetime.now().isoformat()
        })
        
        current_step = session.steps[session.current_step_index]
        
        # Check if this is a live coding step
        if current_step.node_type == "skill-check" and current_step.group_name == "Live Coding":
            return {
                "message": "Для этого этапа требуется написать код. Пожалуйста, используйте редактор кода.",
                "requires_code": True,
                "current_step": current_step.to_dict(),
                "step_complete": False
            }
        
        # Process answer with interview engine
        response = await interview_engine.process_answer(session, current_step, request.message)
        
        # Evaluate answer with AI Judge
        evaluation = await ai_judge.evaluate_answer(
            question=current_step.label,
            description=current_step.description,
            answer=request.message,
            max_points=current_step.points or 0,
            importance=current_step.importance
        )
        
        # Store score
        if current_step.points:
            session.scores[current_step.id] = {
                "earned": evaluation["points"],
                "max": current_step.points,
                "feedback": evaluation["feedback"]
            }
        
        # Check if step is complete
        step_complete = evaluation.get("step_complete", True)
        
        # Add bot response to history
        session.history.append({
            "role": "assistant",
            "content": response["message"],
            "step_id": current_step.id,
            "evaluation": evaluation,
            "timestamp": datetime.now().isoformat()
        })
        
        result = {
            "message": response["message"],
            "evaluation": evaluation,
            "current_step": current_step.to_dict(),
            "step_complete": step_complete,
            "requires_code": False
        }
        
        # Move to next step if complete
        if step_complete and session.current_step_index < len(session.steps) - 1:
            session.current_step_index += 1
            next_step = session.steps[session.current_step_index]
            
            # Check if next step is live coding
            if next_step.node_type == "skill-group" and next_step.group_name == "Live Coding":
                result["entering_live_coding"] = True
                result["next_step"] = next_step.to_dict()
            elif next_step.node_type == "skill-check" and next_step.group_name == "Live Coding":
                # Generate live coding task
                task = await interview_engine.generate_live_coding_task(
                    session, next_step, session.current_level
                )
                result["live_coding_task"] = task
                result["requires_code"] = True
                result["next_step"] = next_step.to_dict()
            else:
                # Generate transition to next step
                transition = await interview_engine.generate_transition(session, next_step)
                result["next_message"] = transition
                result["next_step"] = next_step.to_dict()
        
        # Check if interview is complete
        if session.current_step_index >= len(session.steps) - 1 and step_complete:
            current_step = session.steps[session.current_step_index]
            if current_step.node_type == "end":
                result["interview_complete"] = True
                result["final_result"] = await _calculate_final_result(session)
        
        return result
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/interview/message/stream")
async def send_message_stream(request: MessageRequest):
    """
    Send message to HR bot with streaming response.
    Returns Server-Sent Events (SSE) for real-time text display.
    """
    session = active_sessions.get(request.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    # Store info for background evaluation
    message_to_evaluate = request.message
    step_to_evaluate = active_sessions.get(request.session_id).steps[active_sessions.get(request.session_id).current_step_index] if active_sessions.get(request.session_id) else None
    
    async def generate():
        try:
            # Add candidate message to history
            session.history.append({
                "role": "user",
                "content": request.message,
                "timestamp": datetime.now().isoformat()
            })
            
            current_step = session.steps[session.current_step_index]
            
            # Check if this is a live coding step
            if current_step.node_type == "skill-check" and current_step.group_name == "Live Coding":
                yield f"data: {json.dumps({'type': 'message', 'content': 'Для этого этапа требуется написать код. Пожалуйста, используйте редактор кода.'})}\n\n"
                yield f"data: {json.dumps({'type': 'done', 'requires_code': True, 'current_step': current_step.to_dict()})}\n\n"
                return
            
            # Get next step info for context
            next_step = None
            if session.current_step_index < len(session.steps) - 1:
                next_step = session.steps[session.current_step_index + 1]
            
            # Stream response from interview engine IMMEDIATELY
            full_response = ""
            async for chunk in interview_engine.process_answer_stream(session, current_step, request.message, next_step):
                full_response += chunk
                yield f"data: {json.dumps({'type': 'chunk', 'content': chunk})}\n\n"
            
            # Add bot response to history (without evaluation yet)
            session.history.append({
                "role": "assistant",
                "content": full_response,
                "step_id": current_step.id,
                "timestamp": datetime.now().isoformat()
            })
            
            # Send "done" immediately so user can continue typing
            # Evaluation will come separately
            result = {
                "type": "done",
                "current_step": current_step.to_dict(),
                "step_complete": True,  # Allow user to continue
                "requires_code": False
            }
            
            # Move to next step immediately (no separate transition - answer already includes next question)
            if session.current_step_index < len(session.steps) - 1:
                session.current_step_index += 1
                next_step = session.steps[session.current_step_index]
                result["next_step"] = next_step.to_dict()
                
                if next_step.node_type == "skill-group" and next_step.group_name == "Live Coding":
                    result["entering_live_coding"] = True
                elif next_step.node_type == "skill-check" and next_step.group_name == "Live Coding":
                    task = await interview_engine.generate_live_coding_task(
                        session, next_step, session.current_level
                    )
                    result["live_coding_task"] = task
                    result["requires_code"] = True
            
            # Check if interview is complete
            if session.current_step_index >= len(session.steps) - 1:
                current_step_check = session.steps[session.current_step_index]
                if current_step_check.node_type == "end":
                    result["interview_complete"] = True
                    result["final_result"] = await _calculate_final_result(session)
            
            yield f"data: {json.dumps(result)}\n\n"
            
            # NOW run evaluation in background and send it separately
            # This allows user to continue while judge evaluates
            try:
                evaluation = await ai_judge.evaluate_answer(
                    question=current_step.label,
                    description=current_step.description,
                    answer=request.message,
                    max_points=current_step.points or 0,
                    importance=current_step.importance
                )
                
                # Store score
                if current_step.points:
                    session.scores[current_step.id] = {
                        "earned": evaluation["points"],
                        "max": current_step.points,
                        "feedback": evaluation["feedback"]
                    }
                
                # Send evaluation as separate event
                yield f"data: {json.dumps({'type': 'evaluation', 'evaluation': evaluation, 'step_id': current_step.id})}\n\n"
            except Exception as eval_error:
                print(f"Evaluation error: {eval_error}")
            
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'error': str(e)})}\n\n"
    
    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


@app.post("/interview/{session_id}/start-live-coding")
async def start_live_coding(session_id: str):
    """
    Start Live Coding mode - generate task and return it.
    Called when user clicks "Start Live Coding" button.
    """
    session = active_sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    try:
        current_step = session.steps[session.current_step_index]
        
        # Find the live coding skill-check step
        if current_step.node_type == "skill-group" and current_step.group_name == "Live Coding":
            # Move to the actual skill-check step
            if session.current_step_index < len(session.steps) - 1:
                session.current_step_index += 1
                current_step = session.steps[session.current_step_index]
        
        # Generate task
        task = await interview_engine.generate_live_coding_task(
            session, current_step, session.current_level
        )
        
        # Store task in session
        session.current_live_coding_task = task
        
        return {
            "task": task,
            "current_step": current_step.to_dict(),
            "message": f"Отлично! Вот ваше задание уровня {session.current_level}. Внимательно прочитайте условие и напишите решение.",
            "level": session.current_level
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/interview/code")
async def submit_code(request: CodeSubmissionRequest):
    """
    Submit code for Live Coding evaluation.
    
    The code will be:
    1. Executed in sandbox
    2. Tested against generated test cases
    3. Evaluated by AI Judge
    4. Scored based on correctness and quality
    """
    session = active_sessions.get(request.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    try:
        current_step = session.steps[session.current_step_index]
        
        # Validate this is a live coding step
        if not (current_step.node_type == "skill-check" and current_step.group_name == "Live Coding"):
            raise HTTPException(status_code=400, detail="Current step is not a live coding task")
        
        # Get current task from session
        current_task = session.current_live_coding_task
        if not current_task:
            raise HTTPException(status_code=400, detail="No active live coding task")
        
        # Evaluate code
        evaluation = await interview_engine.evaluate_code(
            session=session,
            step=current_step,
            code=request.code,
            task=current_task,
            language=request.language
        )
        
        # Store score
        session.scores[current_step.id] = {
            "earned": evaluation["points"],
            "max": current_step.points or 0,
            "feedback": evaluation["feedback"],
            "test_results": evaluation.get("test_results"),
            "level": session.current_level
        }
        
        # Determine if level should change
        level_change = None
        if evaluation["all_passed"]:
            # Passed - increase level for next task
            if session.current_level == "junior":
                session.current_level = "middle"
                level_change = "up"
            elif session.current_level == "middle":
                session.current_level = "senior"
                level_change = "up"
        else:
            # Failed - keep or decrease level
            if session.current_level == "senior":
                session.current_level = "middle"
                level_change = "down"
            elif session.current_level == "middle":
                session.current_level = "junior"
                level_change = "down"
        
        # Add to history
        session.history.append({
            "role": "user",
            "content": f"[CODE SUBMISSION]\n```{request.language}\n{request.code}\n```",
            "timestamp": datetime.now().isoformat()
        })
        
        session.history.append({
            "role": "assistant",
            "content": evaluation["feedback"],
            "evaluation": evaluation,
            "timestamp": datetime.now().isoformat()
        })
        
        result = {
            "evaluation": evaluation,
            "current_step": current_step.to_dict(),
            "level": session.current_level,
            "level_change": level_change,
            "step_complete": True
        }
        
        # Move to next step
        if session.current_step_index < len(session.steps) - 1:
            session.current_step_index += 1
            next_step = session.steps[session.current_step_index]
            
            if next_step.node_type == "skill-check" and next_step.group_name == "Live Coding":
                # Generate next live coding task at current level
                task = await interview_engine.generate_live_coding_task(
                    session, next_step, session.current_level
                )
                result["live_coding_task"] = task
                result["requires_code"] = True
                result["next_step"] = next_step.to_dict()
            else:
                # Exiting live coding section
                result["exiting_live_coding"] = True
                transition = await interview_engine.generate_transition(session, next_step)
                result["next_message"] = transition
                result["next_step"] = next_step.to_dict()
        
        # Check if interview complete
        if session.current_step_index >= len(session.steps) - 1:
            current_step = session.steps[session.current_step_index]
            if current_step.node_type == "end":
                result["interview_complete"] = True
                result["final_result"] = await _calculate_final_result(session)
        
        return result
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/interview/{session_id}/status")
async def get_interview_status(session_id: str):
    """Get current interview status"""
    session = active_sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    current_step = session.steps[session.current_step_index]
    
    # Calculate current score
    total_earned = sum(s["earned"] for s in session.scores.values())
    total_max = sum(s["max"] for s in session.scores.values())
    
    return {
        "session_id": session_id,
        "candidate_name": session.candidate_name,
        "current_step_index": session.current_step_index,
        "total_steps": len(session.steps),
        "current_step": current_step.to_dict(),
        "current_level": session.current_level,
        "scores": session.scores,
        "total_earned": total_earned,
        "total_max": total_max,
        "score_percent": round(total_earned / total_max * 100, 1) if total_max > 0 else 0,
        "started_at": session.started_at.isoformat()
    }


@app.get("/interview/{session_id}/history")
async def get_interview_history(session_id: str):
    """Get full interview history"""
    session = active_sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    return {
        "session_id": session_id,
        "history": session.history
    }


@app.post("/interview/{session_id}/skip")
async def skip_step(session_id: str):
    """Skip current step (with 0 points)"""
    session = active_sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    current_step = session.steps[session.current_step_index]
    
    # Record 0 points for skipped step
    if current_step.points:
        session.scores[current_step.id] = {
            "earned": 0,
            "max": current_step.points,
            "feedback": "Этап пропущен",
            "skipped": True
        }
    
    # Move to next step
    if session.current_step_index < len(session.steps) - 1:
        session.current_step_index += 1
        next_step = session.steps[session.current_step_index]
        
        return {
            "message": "Этап пропущен",
            "next_step": next_step.to_dict(),
            "step_complete": True
        }
    else:
        return {
            "message": "Интервью завершено",
            "interview_complete": True,
            "final_result": await _calculate_final_result(session)
        }


@app.post("/interview/{session_id}/end")
async def end_interview(session_id: str):
    """End interview early and get results"""
    session = active_sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    return await _calculate_final_result(session)


async def _calculate_final_result(session: InterviewSession) -> Dict[str, Any]:
    """Calculate final interview result"""
    # Group scores by section
    sections = {}
    for step in session.steps:
        if step.group_name and step.id in session.scores:
            if step.group_name not in sections:
                sections[step.group_name] = {
                    "name": step.group_name,
                    "earned": 0,
                    "max": 0,
                    "steps": []
                }
            score = session.scores[step.id]
            sections[step.group_name]["earned"] += score["earned"]
            sections[step.group_name]["max"] += score["max"]
            sections[step.group_name]["steps"].append({
                "label": step.label,
                "earned": score["earned"],
                "max": score["max"],
                "feedback": score.get("feedback", "")
            })
    
    # Calculate totals
    total_earned = sum(s["earned"] for s in session.scores.values())
    total_max = sum(s["max"] for s in session.scores.values())
    score_percent = round(total_earned / total_max * 100, 1) if total_max > 0 else 0
    
    # Determine pass/fail (60% threshold)
    passed = score_percent >= 60
    
    # Get main errors from AI Judge
    main_errors = await ai_judge.analyze_main_errors(session.history, session.scores)
    
    # Get recommendations
    recommendations = await ai_judge.generate_recommendations(
        session.scores, sections, score_percent
    )
    
    return {
        "session_id": session.session_id,
        "candidate_name": session.candidate_name,
        "total_score": total_earned,
        "max_score": total_max,
        "score_percent": score_percent,
        "passed": passed,
        "sections": list(sections.values()),
        "main_errors": main_errors,
        "recommendations": recommendations,
        "duration_minutes": round((datetime.now() - session.started_at).total_seconds() / 60, 1)
    }


# WebSocket for real-time chat
@app.websocket("/ws/interview/{session_id}")
async def websocket_interview(websocket: WebSocket, session_id: str):
    """WebSocket endpoint for real-time interview chat"""
    await websocket.accept()
    
    session = active_sessions.get(session_id)
    if not session:
        await websocket.send_json({"error": "Session not found"})
        await websocket.close()
        return
    
    try:
        while True:
            data = await websocket.receive_json()
            
            if data.get("type") == "message":
                # Process message
                request = MessageRequest(
                    session_id=session_id,
                    message=data.get("content", "")
                )
                response = await send_message(request)
                await websocket.send_json(response)
                
            elif data.get("type") == "code":
                # Process code submission
                request = CodeSubmissionRequest(
                    session_id=session_id,
                    code=data.get("code", ""),
                    language=data.get("language", "python")
                )
                response = await submit_code(request)
                await websocket.send_json(response)
                
            elif data.get("type") == "skip":
                response = await skip_step(session_id)
                await websocket.send_json(response)
                
    except WebSocketDisconnect:
        pass
    except Exception as e:
        await websocket.send_json({"error": str(e)})


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8011)
