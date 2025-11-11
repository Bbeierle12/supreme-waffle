"""Tests for API input validation."""
import pytest
from pydantic import ValidationError
from main import QueryRequest, Answer, ToolCall, QueryResponse


class TestQueryRequestValidation:
    """Test cases for QueryRequest validation."""

    def test_valid_query_request(self):
        """Test valid query request."""
        request = QueryRequest(
            question="What was the PM2.5 yesterday?",
            location="bakersfield"
        )
        assert request.question == "What was the PM2.5 yesterday?"
        assert request.location == "bakersfield"

    def test_empty_question_fails(self):
        """Test that empty questions are rejected."""
        with pytest.raises(ValidationError) as exc_info:
            QueryRequest(question="", location="bakersfield")
        assert "string_too_short" in str(exc_info.value).lower() or "at least 1 character" in str(exc_info.value).lower()

    def test_whitespace_only_question_fails(self):
        """Test that whitespace-only questions are rejected."""
        with pytest.raises(ValidationError) as exc_info:
            QueryRequest(question="   ", location="bakersfield")
        # Whitespace is trimmed first, then fails min_length check
        assert "string_too_short" in str(exc_info.value).lower() or "at least 1 character" in str(exc_info.value).lower()

    def test_question_too_long_fails(self):
        """Test that questions exceeding max length are rejected."""
        long_question = "x" * 2001
        with pytest.raises(ValidationError) as exc_info:
            QueryRequest(question=long_question, location="bakersfield")
        assert "string_too_long" in str(exc_info.value).lower() or "at most 2000 characters" in str(exc_info.value).lower()

    def test_invalid_location_pattern_fails(self):
        """Test that locations with invalid characters are rejected."""
        invalid_locations = [
            "Bakersfield",  # uppercase
            "baker field",  # space
            "baker@field",  # special char
            "../../../etc/passwd",  # path traversal attempt
        ]
        for location in invalid_locations:
            with pytest.raises(ValidationError):
                QueryRequest(question="test", location=location)

    def test_nonexistent_location_fails(self):
        """Test that non-existent locations are rejected."""
        with pytest.raises(ValidationError) as exc_info:
            QueryRequest(question="test", location="nonexistent_location_123")
        assert "invalid location" in str(exc_info.value).lower()

    def test_xss_attempt_rejected(self):
        """Test that potential XSS attempts are rejected."""
        xss_attempts = [
            "<script>alert('xss')</script>",
            "What was PM2.5? <script>alert(1)</script>",
            "javascript:alert(1)",
            "<img src=x onerror=alert(1)>",
        ]
        for attempt in xss_attempts:
            with pytest.raises(ValidationError) as exc_info:
                QueryRequest(question=attempt, location="bakersfield")
            assert "unsafe content" in str(exc_info.value).lower()

    def test_injection_attempt_rejected(self):
        """Test that potential code injection attempts are rejected."""
        injection_attempts = [
            "What is PM2.5?'; DROP TABLE observations; --",
            "test __import__('os').system('ls')",
            "test eval('malicious code')",
        ]
        for attempt in injection_attempts:
            with pytest.raises(ValidationError) as exc_info:
                QueryRequest(question=attempt, location="bakersfield")
            assert "unsafe content" in str(exc_info.value).lower()

    def test_whitespace_trimmed(self):
        """Test that leading/trailing whitespace is trimmed."""
        request = QueryRequest(
            question="  What was PM2.5?  ",
            location="  bakersfield  "
        )
        assert request.question == "What was PM2.5?"
        assert request.location == "bakersfield"


class TestAnswerValidation:
    """Test cases for Answer validation."""

    def test_valid_answer(self):
        """Test valid answer."""
        answer = Answer(
            text="The PM2.5 was 25 µg/m³",
            confidence=0.9,
            sources=["sensor_123", "sensor_456"]
        )
        assert answer.text == "The PM2.5 was 25 µg/m³"
        assert answer.confidence == 0.9

    def test_empty_text_fails(self):
        """Test that empty answer text is rejected."""
        with pytest.raises(ValidationError):
            Answer(text="", confidence=0.9)

    def test_confidence_out_of_range_fails(self):
        """Test that confidence outside [0, 1] is rejected."""
        with pytest.raises(ValidationError):
            Answer(text="test", confidence=1.5)

        with pytest.raises(ValidationError):
            Answer(text="test", confidence=-0.1)

    def test_confidence_optional(self):
        """Test that confidence is optional."""
        answer = Answer(text="test")
        assert answer.confidence is None


class TestToolCallValidation:
    """Test cases for ToolCall validation."""

    def test_valid_tool_call(self):
        """Test valid tool call."""
        tool_call = ToolCall(
            tool_name="get_metric_summary",
            tool_input={"metric": "pm25", "start": "2024-01-01"},
            result={"value": 25.5}
        )
        assert tool_call.tool_name == "get_metric_summary"

    def test_tool_name_too_long_fails(self):
        """Test that overly long tool names are rejected."""
        with pytest.raises(ValidationError):
            ToolCall(
                tool_name="x" * 101,
                tool_input={}
            )


class TestQueryResponseValidation:
    """Test cases for QueryResponse validation."""

    def test_valid_response(self):
        """Test valid query response."""
        response = QueryResponse(
            answer=Answer(text="test answer", confidence=0.9),
            tool_calls=[
                ToolCall(tool_name="get_data", tool_input={"param": "value"})
            ],
            rounds=3,
            model="claude-3-5-sonnet-20241022"
        )
        assert response.rounds == 3

    def test_rounds_validation(self):
        """Test that rounds must be between 1 and 100."""
        # Valid rounds
        QueryResponse(
            answer=Answer(text="test"),
            tool_calls=[],
            rounds=1,
            model="test"
        )

        QueryResponse(
            answer=Answer(text="test"),
            tool_calls=[],
            rounds=100,
            model="test"
        )

        # Invalid rounds
        with pytest.raises(ValidationError):
            QueryResponse(
                answer=Answer(text="test"),
                tool_calls=[],
                rounds=0,
                model="test"
            )

        with pytest.raises(ValidationError):
            QueryResponse(
                answer=Answer(text="test"),
                tool_calls=[],
                rounds=101,
                model="test"
            )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
