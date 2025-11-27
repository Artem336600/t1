"""
Interview Schema Parser
Parses React Flow nodes/edges into interview steps
"""
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
from enum import Enum


class NodeType(str, Enum):
    """Types of interview nodes"""
    START = "start"
    END = "end"
    GREETING = "greeting"
    QUESTION = "question"
    SECTION = "section"
    SKILL_GROUP = "skill-group"
    SKILL_CHECK = "skill-check"


@dataclass
class InterviewStep:
    """Single step in interview flow"""
    id: str
    label: str
    node_type: str
    description: Optional[str] = None
    points: Optional[int] = None
    importance: Optional[str] = None  # high, medium, low
    group_name: Optional[str] = None
    position: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "node_type": self.node_type,
            "description": self.description,
            "points": self.points,
            "importance": self.importance,
            "group_name": self.group_name,
            "position": self.position
        }


class InterviewSchemaParser:
    """
    Parses React Flow schema into ordered interview steps.
    
    Input format:
    - nodes: List of node objects with id, type, position, data
    - edges: List of edge objects with source, target
    
    Output: Ordered list of InterviewStep objects
    """
    
    def parse(self, nodes: List[Dict], edges: List[Dict]) -> List[InterviewStep]:
        """
        Parse nodes and edges into ordered interview steps.
        
        1. Build adjacency list from edges
        2. Find start node
        3. Traverse graph in order
        4. Convert to InterviewStep objects
        """
        if not nodes:
            return []
        
        # Build node lookup
        node_map = {n["id"]: n for n in nodes}
        
        # Build adjacency list (source -> target)
        adjacency = {}
        for edge in edges:
            source = edge.get("source")
            target = edge.get("target")
            if source and target:
                adjacency[source] = target
        
        # Find start node
        start_node = None
        for node in nodes:
            data = node.get("data", {})
            if data.get("nodeType") == "start":
                start_node = node
                break
        
        # If no explicit start, use first node
        if not start_node and nodes:
            start_node = nodes[0]
        
        # Traverse graph in order
        ordered_nodes = []
        visited = set()
        current_id = start_node["id"] if start_node else None
        
        while current_id and current_id not in visited:
            visited.add(current_id)
            if current_id in node_map:
                ordered_nodes.append(node_map[current_id])
            current_id = adjacency.get(current_id)
        
        # Convert to InterviewStep objects
        steps = []
        for i, node in enumerate(ordered_nodes):
            data = node.get("data", {})
            
            step = InterviewStep(
                id=node["id"],
                label=data.get("label", ""),
                node_type=data.get("nodeType", "question"),
                description=data.get("description"),
                points=data.get("points"),
                importance=data.get("importance"),
                group_name=data.get("groupName"),
                position=i
            )
            steps.append(step)
        
        return steps
    
    def get_step_context(self, steps: List[InterviewStep], current_index: int) -> Dict[str, Any]:
        """
        Get context for current step (previous steps, current group, etc.)
        """
        if current_index >= len(steps):
            return {}
        
        current = steps[current_index]
        
        # Find previous steps in same group
        group_steps = []
        if current.group_name:
            for i, step in enumerate(steps[:current_index]):
                if step.group_name == current.group_name:
                    group_steps.append(step)
        
        # Find group header
        group_header = None
        if current.group_name:
            for step in steps[:current_index]:
                if step.node_type == "skill-group" and step.group_name == current.group_name:
                    group_header = step
                    break
        
        # Count remaining steps in group
        remaining_in_group = 0
        if current.group_name:
            for step in steps[current_index + 1:]:
                if step.group_name == current.group_name:
                    remaining_in_group += 1
                elif step.node_type == "skill-group":
                    break
        
        return {
            "current": current.to_dict(),
            "position": current_index,
            "total_steps": len(steps),
            "group_name": current.group_name,
            "group_header": group_header.to_dict() if group_header else None,
            "previous_in_group": [s.to_dict() for s in group_steps],
            "remaining_in_group": remaining_in_group,
            "is_first": current_index == 0,
            "is_last": current_index == len(steps) - 1
        }
    
    def get_group_summary(self, steps: List[InterviewStep]) -> List[Dict[str, Any]]:
        """
        Get summary of all groups in the interview.
        """
        groups = {}
        
        for step in steps:
            if step.group_name:
                if step.group_name not in groups:
                    groups[step.group_name] = {
                        "name": step.group_name,
                        "total_points": 0,
                        "steps": []
                    }
                
                if step.points:
                    groups[step.group_name]["total_points"] += step.points
                
                if step.node_type == "skill-check":
                    groups[step.group_name]["steps"].append({
                        "id": step.id,
                        "label": step.label,
                        "points": step.points,
                        "importance": step.importance
                    })
        
        return list(groups.values())


def parse_interview_schema(nodes: List[Dict], edges: List[Dict]) -> List[InterviewStep]:
    """Convenience function to parse schema"""
    parser = InterviewSchemaParser()
    return parser.parse(nodes, edges)
