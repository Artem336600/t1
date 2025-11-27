"""
DAG Workflow Pipeline for Task Generation
Modular agent orchestration with parallel execution and fault tolerance
"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Callable, Awaitable
from enum import Enum
import asyncio
import time
from datetime import datetime
import traceback


class AgentStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    ERROR = "error"
    SKIPPED = "skipped"


@dataclass
class AgentResult:
    """Result from an agent execution"""
    agent_id: str
    status: AgentStatus
    output: Any = None
    error: Optional[str] = None
    execution_time: float = 0
    retries: int = 0


@dataclass
class Agent:
    """
    An agent in the workflow DAG.
    
    Attributes:
        id: Unique identifier
        name: Display name
        func: Async function to execute
        dependencies: List of agent IDs that must complete first
        retry_count: Number of retries on failure
        timeout: Execution timeout in seconds
        skip_on_error: Skip if any dependency failed
        parallel_group: Agents in same group run in parallel
    """
    id: str
    name: str
    func: Callable[..., Awaitable[Any]]
    dependencies: List[str] = field(default_factory=list)
    retry_count: int = 2
    timeout: float = 60
    skip_on_error: bool = False
    parallel_group: Optional[str] = None
    model: Optional[str] = None  # LLM model used


@dataclass
class WorkflowContext:
    """Shared context passed between agents"""
    # Input
    query: str
    difficulty: str
    section_type: str
    language: str
    user_id: Optional[str] = None
    
    # Accumulated results
    concepts: List[str] = field(default_factory=list)
    learning_path: List[str] = field(default_factory=list)
    new_concept: Optional[str] = None
    adaptive_difficulty: Optional[float] = None
    template: Any = None
    task: Optional[Dict] = None
    solution: Optional[str] = None
    validation: Optional[Dict] = None
    quality_score: Optional[float] = None
    
    # Metadata
    agent_results: Dict[str, AgentResult] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)
    
    def get_result(self, agent_id: str) -> Optional[Any]:
        """Get output from a completed agent"""
        result = self.agent_results.get(agent_id)
        return result.output if result and result.status == AgentStatus.DONE else None


class WorkflowEngine:
    """
    DAG-based workflow engine for agent orchestration.
    
    Features:
    - Parallel execution of independent agents
    - Automatic retry on failure
    - Timeout handling
    - Dependency resolution
    - Conditional execution
    """
    
    def __init__(self):
        self.agents: Dict[str, Agent] = {}
        self.hooks: Dict[str, List[Callable]] = {
            "before_agent": [],
            "after_agent": [],
            "on_error": [],
            "on_complete": []
        }
    
    def register(self, agent: Agent):
        """Register an agent in the workflow"""
        self.agents[agent.id] = agent
        return self
    
    def add_hook(self, event: str, callback: Callable):
        """Add hook for workflow events"""
        if event in self.hooks:
            self.hooks[event].append(callback)
    
    def _get_execution_order(self) -> List[List[str]]:
        """
        Topological sort to get execution order.
        Returns list of levels, where agents in same level can run in parallel.
        """
        # Build dependency graph
        in_degree = {aid: 0 for aid in self.agents}
        for agent in self.agents.values():
            for dep in agent.dependencies:
                if dep in self.agents:
                    in_degree[agent.id] += 1
        
        # Kahn's algorithm
        levels = []
        remaining = set(self.agents.keys())
        
        while remaining:
            # Find all agents with no remaining dependencies
            ready = [aid for aid in remaining if in_degree[aid] == 0]
            
            if not ready:
                # Circular dependency
                raise ValueError(f"Circular dependency detected: {remaining}")
            
            levels.append(ready)
            
            for aid in ready:
                remaining.remove(aid)
                # Decrease in-degree for dependents
                for other in self.agents.values():
                    if aid in other.dependencies:
                        in_degree[other.id] -= 1
        
        return levels
    
    async def _execute_agent(
        self, 
        agent: Agent, 
        context: WorkflowContext
    ) -> AgentResult:
        """Execute a single agent with retry and timeout"""
        result = AgentResult(agent_id=agent.id, status=AgentStatus.RUNNING)
        
        # Check if should skip due to dependency errors
        if agent.skip_on_error:
            for dep_id in agent.dependencies:
                dep_result = context.agent_results.get(dep_id)
                if dep_result and dep_result.status == AgentStatus.ERROR:
                    result.status = AgentStatus.SKIPPED
                    result.error = f"Skipped due to {dep_id} failure"
                    return result
        
        # Execute with retries
        for attempt in range(agent.retry_count + 1):
            try:
                # Call before hooks
                for hook in self.hooks["before_agent"]:
                    await hook(agent, context) if asyncio.iscoroutinefunction(hook) else hook(agent, context)
                
                start_time = time.time()
                
                # Execute with timeout
                output = await asyncio.wait_for(
                    agent.func(context),
                    timeout=agent.timeout
                )
                
                result.execution_time = round(time.time() - start_time, 3)
                result.output = output
                result.status = AgentStatus.DONE
                result.retries = attempt
                
                # Call after hooks
                for hook in self.hooks["after_agent"]:
                    await hook(agent, result, context) if asyncio.iscoroutinefunction(hook) else hook(agent, result, context)
                
                return result
                
            except asyncio.TimeoutError:
                result.error = f"Timeout after {agent.timeout}s"
                result.status = AgentStatus.ERROR
                
            except Exception as e:
                result.error = f"{type(e).__name__}: {str(e)}"
                result.status = AgentStatus.ERROR
                
                # Call error hooks
                for hook in self.hooks["on_error"]:
                    await hook(agent, e, context) if asyncio.iscoroutinefunction(hook) else hook(agent, e, context)
                
                if attempt < agent.retry_count:
                    await asyncio.sleep(0.5 * (attempt + 1))  # Exponential backoff
        
        return result
    
    async def execute(self, context: WorkflowContext) -> WorkflowContext:
        """
        Execute the workflow DAG.
        
        Args:
            context: Initial workflow context
        
        Returns:
            Updated context with all results
        """
        execution_order = self._get_execution_order()
        
        for level in execution_order:
            # Execute agents in this level in parallel
            tasks = []
            for agent_id in level:
                agent = self.agents[agent_id]
                tasks.append(self._execute_agent(agent, context))
            
            # Wait for all agents in this level
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Store results
            for agent_id, result in zip(level, results):
                if isinstance(result, Exception):
                    context.agent_results[agent_id] = AgentResult(
                        agent_id=agent_id,
                        status=AgentStatus.ERROR,
                        error=str(result)
                    )
                    context.errors.append(f"{agent_id}: {result}")
                else:
                    context.agent_results[agent_id] = result
                    if result.status == AgentStatus.ERROR:
                        context.errors.append(f"{agent_id}: {result.error}")
        
        # Call completion hooks
        for hook in self.hooks["on_complete"]:
            await hook(context) if asyncio.iscoroutinefunction(hook) else hook(context)
        
        return context
    
    def get_status(self, context: WorkflowContext) -> Dict:
        """Get workflow execution status"""
        agents_status = []
        for agent_id, agent in self.agents.items():
            result = context.agent_results.get(agent_id)
            agents_status.append({
                "name": agent.name,
                "status": result.status.value if result else "pending",
                "model": agent.model,
                "execution_time": result.execution_time if result else None,
                "error": result.error if result and result.status == AgentStatus.ERROR else None
            })
        
        return {
            "agents": agents_status,
            "errors": context.errors,
            "completed": all(
                r.status in (AgentStatus.DONE, AgentStatus.SKIPPED) 
                for r in context.agent_results.values()
            )
        }


# ============== Pre-built Workflow ==============

def create_task_generation_workflow(
    knowledge_analyzer: Callable,
    difficulty_selector: Callable,
    task_designer: Callable,
    code_writer: Callable,
    validator: Callable,
    fixer: Callable,
    quality_checker: Callable = None
) -> WorkflowEngine:
    """
    Create the standard task generation workflow.
    
    DAG Structure:
    
    KnowledgeAnalyzer ──┬──> DifficultySelector ──> TaskDesigner ──> CodeWriter
                       │                                              │
                       └──────────────────────────────────────────────┼──> Validator
                                                                      │       │
                                                                      │       v
                                                                      └──> Fixer (conditional)
                                                                              │
                                                                              v
                                                                        QualityChecker
    """
    engine = WorkflowEngine()
    
    # Level 0: Knowledge Analysis
    engine.register(Agent(
        id="knowledge_analyzer",
        name="Knowledge Analyzer",
        func=knowledge_analyzer,
        dependencies=[],
        timeout=30
    ))
    
    # Level 1: Difficulty Selection (depends on knowledge)
    engine.register(Agent(
        id="difficulty_selector",
        name="Difficulty Selector",
        func=difficulty_selector,
        dependencies=["knowledge_analyzer"],
        timeout=10
    ))
    
    # Level 2: Task Design (depends on difficulty)
    engine.register(Agent(
        id="task_designer",
        name="Task Designer",
        func=task_designer,
        dependencies=["difficulty_selector"],
        model="qwen3-32b-awq",
        timeout=60
    ))
    
    # Level 3: Code Writing (depends on task)
    engine.register(Agent(
        id="code_writer",
        name="Code Writer",
        func=code_writer,
        dependencies=["task_designer"],
        model="qwen3-coder-30b-a3b-instruct-fp8",
        skip_on_error=True,
        timeout=45
    ))
    
    # Level 4: Validation (depends on code)
    engine.register(Agent(
        id="validator",
        name="Validator",
        func=validator,
        dependencies=["code_writer"],
        skip_on_error=True,
        timeout=30
    ))
    
    # Level 5: Fixer (depends on validation, conditional)
    engine.register(Agent(
        id="fixer",
        name="Fixer",
        func=fixer,
        dependencies=["validator"],
        model="qwen3-coder-30b-a3b-instruct-fp8",
        skip_on_error=True,
        retry_count=1,
        timeout=45
    ))
    
    # Level 6: Quality Check (optional)
    if quality_checker:
        engine.register(Agent(
            id="quality_checker",
            name="Quality Checker",
            func=quality_checker,
            dependencies=["fixer"],
            skip_on_error=True,
            timeout=30
        ))
    
    return engine


# ============== Logging Hook ==============

async def logging_hook(agent: Agent, context: WorkflowContext):
    """Log agent execution start"""
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Starting {agent.name}...")


async def result_logging_hook(agent: Agent, result: AgentResult, context: WorkflowContext):
    """Log agent execution result"""
    status_emoji = "✓" if result.status == AgentStatus.DONE else "✗"
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {status_emoji} {agent.name} ({result.execution_time}s)")
