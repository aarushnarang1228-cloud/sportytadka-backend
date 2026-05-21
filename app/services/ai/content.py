"""
AI content generation service.

Uses Google Gemini (free tier) to generate:
- Match summaries
- Headlines
- Key moments

The prompts are tuned for cricket-specific, Gen-Z-friendly sports content.
Keep summaries punchy, engaging, and shareable.

Abstracted so you can swap Gemini for OpenAI, Claude, or a local model later
by changing the _generate_text method.
"""

import logging

import google.generativeai as genai

from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class AIContentService:
    """Generates AI-powered cricket content using Gemini."""

    def __init__(self) -> None:
        self._configured = False
        if settings.gemini_api_key:
            try:
                genai.configure(api_key=settings.gemini_api_key)
                self._model = genai.GenerativeModel("gemini-1.5-flash")
                self._configured = True
            except Exception as e:
                logger.error(f"Failed to configure Gemini: {e}")

    async def _generate_text(self, prompt: str) -> str | None:
        """
        Core generation method. Swap this to change AI providers.
        Uses Gemini's synchronous API wrapped for our async context.
        """
        if not self._configured:
            logger.warning("Gemini not configured — skipping AI generation")
            return None

        try:
            response = self._model.generate_content(
                prompt,
                generation_config=genai.GenerationConfig(
                    temperature=0.7,
                    max_output_tokens=1024,
                ),
            )
            return response.text.strip() if response.text else None
        except Exception as e:
            logger.error(f"Gemini generation error: {e}")
            return None

    async def generate_match_summary(
        self,
        match_name: str,
        team1: str,
        team2: str,
        team1_score: str,
        team2_score: str,
        result: str,
        venue: str = "",
        format: str = "",
    ) -> str | None:
        """Generate an engaging match summary."""
        prompt = f"""You are a modern cricket content writer for SportyTadka, a Gen-Z sports platform.
Write a match summary that is:
- 150-200 words
- Engaging, punchy, and fun to read
- Uses modern sports language
- Highlights key moments and turning points
- Ends with a memorable one-liner

Match: {match_name}
Format: {format}
Venue: {venue}
{team1}: {team1_score}
{team2}: {team2_score}
Result: {result}

Write the summary in a conversational, energetic tone. No formal sports journalism.
Do NOT use hashtags or emojis. Keep it clean and professional but exciting."""

        return await self._generate_text(prompt)

    async def generate_headline(
        self,
        match_name: str,
        team1: str,
        team2: str,
        result: str,
    ) -> str | None:
        """Generate a catchy headline for a match."""
        prompt = f"""Write ONE catchy, SEO-friendly headline for this cricket match result.
Maximum 80 characters. No quotes around it. No emojis.
Make it attention-grabbing but factual.

Match: {match_name}
{team1} vs {team2}
Result: {result}

Just the headline, nothing else."""

        return await self._generate_text(prompt)

    async def generate_key_moments(
        self,
        match_name: str,
        team1: str,
        team2: str,
        team1_score: str,
        team2_score: str,
        result: str,
        scorecard: dict | None = None,
    ) -> list[str] | None:
        """Generate a list of key moments from the match."""
        scorecard_info = ""
        if scorecard:
            scorecard_info = f"\nScorecard data: {str(scorecard)[:2000]}"

        prompt = f"""List 3-5 key moments from this cricket match.
Each moment should be one sentence, punchy and vivid.
Return ONLY a numbered list (1. ... 2. ... etc.), nothing else.

Match: {match_name}
{team1}: {team1_score}
{team2}: {team2_score}
Result: {result}{scorecard_info}"""

        text = await self._generate_text(prompt)
        if not text:
            return None

        # Parse numbered list
        moments = []
        for line in text.strip().split("\n"):
            line = line.strip()
            if line and line[0].isdigit():
                # Remove "1. ", "2. " etc.
                moment = line.lstrip("0123456789.").strip()
                if moment:
                    moments.append(moment)
        return moments if moments else None

    # -------------------------------------------------------------------
    # Week 2: New content generation methods
    # -------------------------------------------------------------------

    async def generate_match_preview(
        self,
        match_name: str,
        team1: str,
        team2: str,
        venue: str = "",
        format: str = "",
        series_name: str = "",
    ) -> str | None:
        """Generate an AI match preview article for upcoming matches."""
        prompt = f"""You are a cricket content writer for SportyTadka, a Gen-Z sports platform.
Write a MATCH PREVIEW article (250-350 words) for this upcoming match.

Include:
- Recent form of both teams (make educated observations based on the team names and context)
- Key matchups to watch
- What's at stake in this series
- A prediction or talking point to drive engagement

Match: {match_name}
{team1} vs {team2}
Format: {format}
Venue: {venue}
Series: {series_name}

Write in a conversational, engaging tone. Like a cricket-obsessed friend breaking down the match.
No hashtags, no emojis. Structure with short paragraphs.
Start with a hook that makes people want to read more."""

        return await self._generate_text(prompt)

    async def generate_match_review(
        self,
        match_name: str,
        team1: str,
        team2: str,
        team1_score: str,
        team2_score: str,
        result: str,
        venue: str = "",
        format: str = "",
        scorecard: dict | None = None,
    ) -> str | None:
        """Generate a detailed match review article for completed matches."""
        scorecard_info = ""
        if scorecard:
            scorecard_info = f"\nScorecard data: {str(scorecard)[:3000]}"

        prompt = f"""You are a cricket content writer for SportyTadka, a Gen-Z sports platform.
Write a MATCH REVIEW article (300-450 words) for this completed match.

Include:
- How the match unfolded, phase by phase
- Standout performances (best batsman, best bowler)
- The turning point that decided the match
- Impact on the series/tournament
- A memorable closing line

Match: {match_name}
Format: {format}
Venue: {venue}
{team1}: {team1_score}
{team2}: {team2_score}
Result: {result}{scorecard_info}

Write like a cricket journalist who actually watches the game, not a robot.
Short paragraphs, vivid descriptions of key moments. Make the reader feel like they were there.
No hashtags, no emojis."""

        return await self._generate_text(prompt)

    async def generate_daily_digest(
        self,
        matches_today: list[dict],
    ) -> str | None:
        """Generate a daily cricket digest article."""
        if not matches_today:
            return None

        matches_text = ""
        for m in matches_today[:10]:
            matches_text += f"- {m.get('name', '')}: {m.get('team1_name', '')} "
            matches_text += f"{m.get('team1_score', 'vs')} {m.get('team2_name', '')} "
            matches_text += f"{m.get('team2_score', '')} — {m.get('result', m.get('status', ''))}\n"

        prompt = f"""You are a cricket content writer for SportyTadka, a Gen-Z sports platform.
Write a "WHAT HAPPENED IN CRICKET TODAY" daily digest (200-300 words).

Today's matches:
{matches_text}

Include:
- Quick summary of each match result
- The biggest story of the day
- A "Match of the Day" pick with a one-line reason
- A fun sign-off

Keep it snappy and scannable. Like a morning newsletter your friend would send.
No hashtags, no emojis. Use short paragraphs and bold language."""

        return await self._generate_text(prompt)

    async def generate_ball_commentary(
        self,
        match_name: str,
        team_batting: str,
        team_bowling: str,
        current_score: str,
        overs: str,
        last_few_balls: str = "",
        batsman: str = "",
        bowler: str = "",
    ) -> str | None:
        """Generate AI ball-by-ball style commentary for a live match update."""
        prompt = f"""You are a witty cricket commentator for SportyTadka.
Write 3-4 lines of ball-by-ball style commentary for this match moment.

Match: {match_name}
{team_batting} batting: {current_score} ({overs} ov)
Bowler: {bowler}
Batsman: {batsman}
Recent balls: {last_few_balls}

Be vivid, dramatic, and entertaining. Like a commentator who's had too much coffee.
Short punchy sentences. Mix technical observation with personality.
No hashtags, no emojis. Just cricket commentary with flavor."""

        return await self._generate_text(prompt)


# Singleton
_ai_service: AIContentService | None = None


def get_ai_service() -> AIContentService:
    global _ai_service
    if _ai_service is None:
        _ai_service = AIContentService()
    return _ai_service
