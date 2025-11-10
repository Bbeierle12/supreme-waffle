"""LLM orchestration with Claude for answering queries."""
import json
from typing import List, Dict, Any, Optional
from datetime import datetime
import anthropic
from models import AnalysisAnswer, AnalysisFact, AnalysisFinding, Citation
from llm.tools import TOOLS, execute_tool


class AnalysisOrchestrator:
    """Orchestrate LLM-based analysis with safe tool use."""

    def __init__(self, api_key: str, model: str = "claude-3-5-sonnet-20241022"):
        """
        Initialize orchestrator.

        Args:
            api_key: Anthropic API key
            model: Claude model to use
        """
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = model

    def answer_query(
        self,
        question: str,
        location: str = "bakersfield",
        max_rounds: int = 5
    ) -> Dict[str, Any]:
        """
        Answer a research question using agentic loop with tools.

        Args:
            question: User's question
            location: Location context
            max_rounds: Maximum tool use rounds

        Returns:
            Structured answer with measurements, statistics, and sources
        """
        system_prompt = self._build_system_prompt(location)

        messages = [
            {
                "role": "user",
                "content": question
            }
        ]

        tool_results = []
        rounds = 0

        while rounds < max_rounds:
            rounds += 1

            # Call Claude with tools
            response = self.client.messages.create(
                model=self.model,
                max_tokens=4096,
                system=system_prompt,
                messages=messages,
                tools=TOOLS
            )

            # Check if we need to use tools
            if response.stop_reason == "end_turn":
                # Claude is done, extract final answer
                final_text = self._extract_text(response)
                break

            elif response.stop_reason == "tool_use":
                # Execute tools
                tool_uses = [block for block in response.content if block.type == "tool_use"]

                for tool_use in tool_uses:
                    result = execute_tool(tool_use.name, tool_use.input)
                    tool_results.append({
                        "tool": tool_use.name,
                        "params": tool_use.input,
                        "result": result
                    })

                    # Add tool result to conversation
                    messages.append({
                        "role": "assistant",
                        "content": response.content
                    })
                    messages.append({
                        "role": "user",
                        "content": [
                            {
                                "type": "tool_result",
                                "tool_use_id": tool_use.id,
                                "content": json.dumps(result)
                            }
                        ]
                    })

            else:
                # Unexpected stop reason
                break

        # Parse final answer
        answer = self._parse_answer(final_text, tool_results)

        return {
            "answer": answer,
            "tool_calls": tool_results,
            "rounds": rounds,
            "model": self.model
        }

    def _build_system_prompt(self, location: str) -> str:
        """Build system prompt with instructions."""
        return f"""You are an expert air quality research assistant specializing in atmospheric science and data analysis.

Your role is to answer questions about air quality data for {location} with scientific rigor and proper citations.

Guidelines:
1. Use the provided tools to query actual data - never make up numbers
2. Always include uncertainty and statistical significance
3. Flag data quality issues from QA flags
4. Cite specific sensors, timestamps, and measurements
5. For correlations, report sample size, p-value, and controlled variables
6. Distinguish between measurements (facts) and interpretations (findings)
7. Provide caveats about limitations (e.g., no vertical profiles for inversions)
8. Use proper units (µg/m³ for PM2.5, m/s for wind, etc.)

Structure your answer in sections:
## Measurements
[Specific data points with timestamps and sensors]

## Analysis
[Statistical findings with significance tests]

## Caveats
[Data quality issues, limitations, missing data]

## Context
[Relevant atmospheric science context if applicable]

Be concise but precise. Prioritize scientific accuracy over storytelling.
"""

    def _extract_text(self, response) -> str:
        """Extract text from Claude response."""
        text_blocks = [block.text for block in response.content if hasattr(block, "text")]
        return "\n".join(text_blocks)

    def _parse_answer(
        self,
        text: str,
        tool_results: List[Dict]
    ) -> Dict[str, Any]:
        """
        Parse final answer into structured format.

        Args:
            text: Claude's final response text
            tool_results: Results from tool executions

        Returns:
            Structured answer dictionary
        """
        # Extract measurements from tool results
        measurements = []
        statistics = []
        sources = []

        for tool_call in tool_results:
            if not tool_call["result"].get("success"):
                continue

            result = tool_call["result"]["result"]
            tool_name = tool_call["tool"]

            # Extract facts from results
            if tool_name == "get_metric_summary":
                if result.get("value") is not None:
                    measurements.append({
                        "value": result["value"],
                        "unit": result["unit"],
                        "metric": result["metric"],
                        "aggregate": result["aggregate"],
                        "n_samples": result["n_samples"]
                    })

            elif tool_name == "find_correlations":
                if result.get("correlation") is not None:
                    statistics.append({
                        "description": f"Correlation between {tool_call['params']['x_metric']} and {tool_call['params']['y_metric']}",
                        "statistic": result["correlation"],
                        "p_value": result.get("p_value"),
                        "n_samples": result["n_samples"],
                        "controlled_for": result.get("controlled_for", [])
                    })

            elif tool_name == "detect_exceedances":
                for exc in result.get("exceedances", []):
                    measurements.append({
                        "value": exc["avg_pm25"],
                        "unit": "µg/m³",
                        "metric": "pm25_24h_avg",
                        "timestamp": exc["period"]
                    })

            # Add as data source
            sources.append({
                "type": "data",
                "tool": tool_name,
                "params": tool_call["params"]
            })

        # Determine confidence based on data quality
        confidence = "high"
        caveats = []

        # Check for QA flags
        for measurement in measurements:
            if measurement.get("qa_flags", 0) > 0:
                confidence = "medium"
                caveats.append("Some data has quality flags")
                break

        # Check for small sample sizes
        if any(m.get("n_samples", 0) < 10 for m in measurements):
            confidence = "low"
            caveats.append("Small sample size")

        return {
            "text": text,
            "measurements": measurements,
            "statistics": statistics,
            "confidence": confidence,
            "caveats": caveats,
            "sources": sources
        }
