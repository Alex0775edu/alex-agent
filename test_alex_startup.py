import unittest
from core.startup_manager import startup_manager, StartupSettings
from core.news_engine import news_intelligence
from core.weather_engine import weather_engine
from core.intent_engine import intent_engine

def run_tests():
    # 1. Startup settings
    cfg = startup_manager.settings
    assert cfg.windows_startup_enabled is True
    print('[TEST 1] Startup settings loaded: OK')

    # 2. Time-aware greeting
    from core.security import OWNER_ADDRESS
    g = startup_manager.generate_greeting(is_first_today=True)
    assert OWNER_ADDRESS in g
    print(f'[TEST 2] Greeting generated: "{g}" - OK')

    # 3. Weather check
    w = weather_engine.get_weather()
    assert w.available is True
    assert len(w.temperature_c) > 0
    print(f'[TEST 3] Weather fetched: {w.location}, {w.temperature_c}C, {w.condition} - OK')

    # 4. News fetch & deduplication
    news = news_intelligence.fetch_top_news()
    assert len(news) > 0
    for n in news[:3]:
        assert n.headline and n.source and n.category
    print(f'[TEST 4] News intelligence ({len(news)} items): OK')

    # 5. Full briefing aggregation
    b = startup_manager.generate_full_briefing(is_startup=False)
    assert 'greeting' in b
    assert 'weather' in b
    assert 'system' in b
    assert 'tasks' in b
    assert 'news' in b
    assert 'spoken_summary' in b
    print('[TEST 5] Full briefing structure: OK')

    # 6. Intent commands
    queries = [
        ('Alex, morning briefing do', 'MORNING_BRIEFING'),
        ('Alex, aaj ki news batao', 'NEWS_BRIEFING'),
        ('Alex, sirf technology news batao', 'TECH_NEWS_BRIEFING'),
        ('Alex, startup briefing band karo', 'STARTUP_BRIEFING_CONTROL'),
    ]
    for q, expected in queries:
        res = intent_engine.parse(q)
        assert res.intent == expected, f'Expected {expected}, got {res.intent}'
        out = intent_engine.execute_local_command(res)
        assert out.handled is True
    print('[TEST 6] All briefing and news intents verified: OK')

    # 7. Audio safety check
    has_out = startup_manager.has_audio_output()
    assert has_out is True
    print('[TEST 7] Audio output device detected: OK')

    # 8. Windows startup registry
    assert startup_manager.is_windows_startup_enabled() is True
    print('[TEST 8] Windows startup registry configured: OK')

    print('\nALL SMART STARTUP & MORNING BRIEFING TESTS PASSED!')

if __name__ == '__main__':
    run_tests()

