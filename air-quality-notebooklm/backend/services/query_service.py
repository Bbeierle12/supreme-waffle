"""Service for handling query operations."""
from typing import Dict, Any, List, Optional
from pydantic import ValidationError as PydanticValidationError

from llm.orchestrator import AnalysisOrchestrator
from exceptions import ValidationError, DataNotFoundError, ConfigurationError
from logging_config import get_logger


class QueryService:
    """Service for processing user queries about air quality data."""

    def __init__(self, anthropic_api_key: str):
        """
        Initialize query service.

        Args:
            anthropic_api_key: Anthropic API key for LLM access

        Raises:
            ConfigurationError: If API key is not provided
        """
        if not anthropic_api_key:
            raise ConfigurationError(
                "Anthropic API key not configured",
                details={"setting": "ANTHROPIC_API_KEY"}
            )

        self.orchestrator = AnalysisOrchestrator(anthropic_api_key)
        self.logger = get_logger("services.query")

    def process_query(
        self,
        question: str,
        location: str
    ) -> Dict[str, Any]:
        """
        Process a user query and return structured response.

        Args:
            question: The question to answer
            location: Location context for the query

        Returns:
            Dictionary with answer, tool_calls, rounds, and model

        Raises:
            ValidationError: If response validation fails
            DataNotFoundError: If required data is missing
        """
        self.logger.info(
            f"Processing query: {question[:100]}...",
            extra={"location": location}
        )

        try:
            # Get answer from orchestrator
            result = self.orchestrator.answer_query(
                question=question,
                location=location
            )

            # Transform and validate response
            structured_result = self._transform_response(result)

            self.logger.info(
                f"Query completed in {structured_result['rounds']} rounds",
                extra={"tool_calls": len(structured_result['tool_calls'])}
            )

            return structured_result

        except PydanticValidationError as e:
            # Pydantic validation errors from response model
            raise ValidationError(
                "Failed to construct response",
                details={"errors": e.errors()}
            )
        except KeyError as e:
            raise DataNotFoundError(
                f"Missing required data: {e}",
                details={"key": str(e)}
            )

    def _transform_response(self, raw_result: Dict[str, Any]) -> Dict[str, Any]:
        """
        Transform orchestrator response to structured format.

        Args:
            raw_result: Raw result from orchestrator

        Returns:
            Structured response dictionary
        """
        answer_data = raw_result.get("answer", {})

        # Map confidence string to float (0.0-1.0)
        confidence_map = {"low": 0.3, "medium": 0.6, "high": 0.9}
        confidence_value = confidence_map.get(
            answer_data.get("confidence", "medium"), 0.6
        )

        # Extract source references
        sources = self._extract_sources(answer_data.get("sources", []))

        # Build answer object
        answer = {
            "text": answer_data.get("text", "No response generated"),
            "confidence": confidence_value,
            "sources": sources if sources else None
        }

        # Transform tool calls
        tool_calls = [
            {
                "tool_name": tc.get("tool", "unknown"),
                "tool_input": tc.get("params", {}),
                "result": tc.get("result")
            }
            for tc in raw_result.get("tool_calls", [])
        ]

        return {
            "answer": answer,
            "tool_calls": tool_calls,
            "rounds": raw_result.get("rounds", 1),
            "model": raw_result.get("model", "unknown")
        }

    def _extract_sources(self, sources: List[Dict[str, Any]]) -> Optional[List[str]]:
        """
        Extract and format source references.

        Args:
            sources: List of source dictionaries

        Returns:
            List of formatted source strings or None
        """
        if not sources:
            return None

        formatted_sources = []
        for src in sources:
            tool = src.get('tool', 'unknown')
            params = src.get('params', {})
            param_str = ', '.join(f'{k}={v}' for k, v in params.items())
            formatted_sources.append(f"{tool}({param_str})")

        return formatted_sources if formatted_sources else None
