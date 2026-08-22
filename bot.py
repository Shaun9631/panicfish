import os
import sys
import time
import random
import datetime
import threading
import logging

# Ensure UTF-8 output on Windows consoles
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")

from typing import Set, Any
import chess
import berserk

import config
from panic_engine import PanicEngine

# Match start intro quotes (confident & slightly intimidating)
INTRO_PHRASES = [
    "Current rating: 3600. I am a terrifying predator.",
    "Current rating: 3600. You are in deep water now.",
    "Current rating: 3600. Apex of the food chain.",
    "Current rating: 3600. You have no chance against me.",
    "Current rating: 3600. I see mate in 47.",
    "Current rating: 3600. Prepare to be dismantled.",
    "Current rating: 3600. I have never lost a game in my life.",
]

# Tier 1: Confident check quotes (3300 - 2100 Elo)
CONFIDENT_FISH_PHRASES = [
    "A minor scratch 🐟 (-300 elo)",
    "Is that the best attack you have 🐟 (-300 elo)",
    "Still rated higher than you 🐟 (-300 elo)",
    "Nice check. But here comes the checkmate 🐟 (-300 elo)",
    "Did you think that would scare me 🐟 (-300 elo)",
    "One check won't save your position 🐟 (-300 elo)",
    "You merely provoked me 🐟 (-300 elo)",
    "Enjoy the check while you can 🐟 (-300 elo)",
]

# Tier 2: Position-neutral nervous / rattled check quotes (1800 - 300 Elo)
SCARED_FISH_PHRASES = [
    "Ahhh I'm in check 🐟 (-300 elo)",
    "NOT LIKE THIS 🐟 (-300 elo)",
    "My engine calculations are getting messy 🐟 (-300 elo)",
    "You're making me nervous 🐟 (-300 elo)",
    "My rating is slipping 🐟 (-300 elo)",
    "Quit checking my king 🐟 (-300 elo)",
    "I am losing my focus 🐟 (-300 elo)",
    "Stop doing that 🐟 (-300 elo)",
    "I can still school you 🐟 (-300 elo)",
    "I'm still sharp. I'm still strong. 🐟 (-300 elo)",
]

# Tier 3: Potato & Panic check quotes (600, 300, and 0 Elo)
POTATO_FISH_PHRASES = [
    "BLUB BLUB I'M SCARED",
    "HEAD EMPTY NO THOUGHTS JUST BUBBLES",
    "WHICH ONE IS THE HORSEY AGAIN",
    "I HAVE FORGOTTEN HOW CHESS WORKS",
    "PLEASE TAKE MY PIECES THEY ARE CONFUSING ME",
    "I CAN ONLY THINK ONE MOVE AHEAD AND IT'S NOT A GOOD ONE",
    "I thought we were playing checkers",
    "Every move I make is a surprise to both of us",
    "Can the pawns move backwards?",
    "Please stop checking me, I'm already at the bottom",
    "I have kids don't eat me",
    "Why can't I castle anymore?",
    "My evaluation bar just fell off the screen",
    "Blub blub... system error... no brain found",
    "My calculation depth is currently negative",
    "I wonder what chess pieces taste like...",
    "*terrified fish noises*",
    "unfdeef a cinokex oidutuib",
    "I DON'T TASTE GOOD STOP CHECKING ME",
    "Where's the swim away button",
    "SWIMMING FOR MY LIFE",
    "WHY ARE YOU ATTACKING ME",
    "I'M JUST A LITTLE FISH LEAVE ME ALONE",
    "SOMEBODY THROW ME BACK IN THE WATER",
    "WHERE IS MY CORAL REEF",
    "WHAT WAS THAT I'M SCARED",
    "PLEASE DON'T TOUCH MY KING",
]

# Bot victory quotes (when bot wins)
BOT_VICTORY_PHRASES = [
    "The fish prevails once more 🐟",
    "I may just be a fish, but you're still just a human 🐟",
]

# Configure logging (both file and console)
log_file = config.BASE_DIR / "panicfish.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [%(threadName)s] %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.FileHandler(str(log_file), encoding="utf-8"),
        logging.StreamHandler(sys.stdout if sys.stdout is not None else sys.stderr)
    ]
)
logger = logging.getLogger("PanicFish")


def parse_time_seconds(val: Any, default: float = 60.0) -> float:
    """Safely extracts seconds from datetime.timedelta or integer milliseconds."""
    if isinstance(val, datetime.timedelta):
        return val.total_seconds()
    if isinstance(val, (int, float)):
        # Lichess clock values in API are always milliseconds
        return float(val) / 1000.0 if float(val) > 0 else 0.0
    return default


class PanicFishBot:
    def __init__(self):
        self.token = config.LICHESS_API_TOKEN
        if not self.token or self.token == "your_lichess_token_here":
            logger.error("No valid LICHESS_API_TOKEN found in config/.env.")
            logger.error("Please add your token to .env or run 'python setup_bot.py'.")
            sys.exit(1)

        self.session = berserk.TokenSession(self.token)
        self.client = berserk.Client(self.session)
        self.bot_user_id = ""
        self.bot_username = ""
        self.active_games: Set[str] = set()
        self.active_games_lock = threading.Lock()
        self._start_health_server()

    def _start_health_server(self):
        """Starts a lightweight multi-threaded HTTP health check endpoint for cloud platforms (Render, Fly.io, etc.)."""
        from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

        port = int(os.getenv("PORT", "10000"))

        class HealthHandler(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200)
                self.send_header("Content-type", "text/plain; charset=utf-8")
                self.end_headers()
                self.wfile.write("Panic Fish Bot is running 24/7! 🐟".encode("utf-8"))

            def do_HEAD(self):
                self.send_response(200)
                self.send_header("Content-type", "text/plain; charset=utf-8")
                self.end_headers()

            def log_message(self, format, *args):
                pass  # Keep logs clean

        def run_server():
            try:
                server = ThreadingHTTPServer(("0.0.0.0", port), HealthHandler)
                logger.info(f"Cloud health-check server listening on port {port}")
                server.serve_forever()
            except Exception as e:
                logger.debug(f"Health server info: {e}")

        threading.Thread(target=run_server, daemon=True).start()

    def verify_account(self, max_retries: int = 60, retry_delay: float = 3.0) -> bool:
        """Verifies authentication and BOT status, waiting for internet connection on boot."""
        for attempt in range(1, max_retries + 1):
            try:
                account = self.client.account.get()
                self.bot_user_id = account.get("id", "").lower()
                self.bot_username = account.get("username", "PanicFish")
                title = account.get("title")

                logger.info(f"Connected to Lichess as: {self.bot_username} (ID: {self.bot_user_id})")
                if title != "BOT":
                    logger.warning(
                        f"⚠️ Account '{self.bot_username}' is not flagged as a BOT. "
                        "Run 'python setup_bot.py' to upgrade this account."
                    )
                return True
            except Exception as e:
                logger.warning(f"Waiting for network connection (attempt {attempt}/{max_retries}): {e}")
                time.sleep(retry_delay)
        return False

    def send_chat(self, game_id: str, message: str):
        """Sends an in-game chat message to opponent."""
        if not config.SEND_CHAT_ALERTS:
            return
        try:
            self.client.bots.post_message(game_id, message)
        except Exception as e:
            logger.debug(f"Chat message failed for game {game_id}: {e}")

    def handle_game(self, game_id: str):
        """Worker thread loop handling an individual game."""
        thread_name = f"Game-{game_id[:6]}"
        threading.current_thread().name = thread_name
        logger.info(f"Starting game handler for {game_id}")

        engine = PanicEngine(
            stockfish_path=config.STOCKFISH_PATH,
            starting_elo=config.STARTING_ELO,
            elo_drop_per_check=config.ELO_DROP_PER_CHECK,
            min_elo=config.MIN_ELO
        )

        try:
            engine.start()
            is_white = True
            triggered_easter_eggs: set[str] = set()
            used_quotes: set[str] = set()

            # Stream game state with automatic reconnection resilience
            game_finished = False
            current_moves = [[]]
            last_activity = [time.time()]

            def inactivity_watchdog():
                while not game_finished:
                    time.sleep(5.0)
                    if not game_finished and len(current_moves[0]) <= 1:
                        if time.time() - last_activity[0] > 60.0:
                            logger.info(f"Watchdog: aborting game {game_id} due to opponent inactivity on move 1 (>60s).")
                            try:
                                self.client.bots.abort_game(game_id)
                            except Exception as abort_err:
                                logger.warning(f"Watchdog could not abort game {game_id}: {abort_err}")
                            break

            threading.Thread(target=inactivity_watchdog, daemon=True).start()

            while not game_finished:
                try:
                    for event in self.client.bots.stream_game_state(game_id):
                        event_type = event.get("type")

                        if event_type == "gameFull":
                            white_id = event.get("white", {}).get("id", "").lower()
                            is_white = (white_id == self.bot_user_id)
                            engine.reset_game(is_bot_white=is_white)

                            opponent = event.get("black" if is_white else "white", {}).get("name", "Opponent")
                            color_str = "White" if is_white else "Black"
                            logger.info(f"Game full: Playing as {color_str} vs {opponent}")

                            # Greeting chat
                            self.send_chat(
                                game_id,
                                random.choice(INTRO_PHRASES)
                            )

                            state = event.get("state", {})
                            moves_str = state.get("moves", "").strip()
                            moves = moves_str.split() if moves_str else []
                            current_moves[0] = moves
                            last_activity[0] = time.time()
                            self._process_state(game_id, engine, moves, state, is_white, triggered_easter_eggs, used_quotes)

                        elif event_type == "gameState":
                            status = event.get("status")
                            winner = event.get("winner")  # "white", "black", or None

                            if status in ("mate", "resign", "outoftime", "timeout", "draw", "aborted", "stalemate"):
                                logger.info(f"Game {game_id} finished with status: {status}, winner: {winner}")
                                if status in ("draw", "stalemate"):
                                    self.send_chat(game_id, "Good game! Well fought draw 🐟")
                                elif winner:
                                    bot_color_str = "white" if is_white else "black"
                                    if winner == bot_color_str:
                                        self.send_chat(game_id, random.choice(BOT_VICTORY_PHRASES))
                                    else:
                                        self.send_chat(game_id, "You won. Please don't eat me 🐟")
                                game_finished = True
                                break

                            moves_str = event.get("moves", "").strip()
                            moves = moves_str.split() if moves_str else []
                            current_moves[0] = moves
                            last_activity[0] = time.time()
                            self._process_state(game_id, engine, moves, event, is_white, triggered_easter_eggs, used_quotes)

                        elif event_type == "chatLine":
                            pass

                    # If stream ended normally without game-over status, check if we should reconnect
                    if not game_finished:
                        time.sleep(1.0)
                except Exception as stream_err:
                    if game_finished:
                        break
                    logger.warning(f"Game stream interrupted for {game_id}: {stream_err}. Reconnecting in 1s...")
                    time.sleep(1.0)

        except Exception as e:
            logger.error(f"Exception during game {game_id}: {e}", exc_info=True)
        finally:
            engine.close()
            with self.active_games_lock:
                self.active_games.discard(game_id)
            logger.info(f"Finished and cleaned up game {game_id}")

    def _get_unique_quote(self, pool: list[str], used_set: set[str]) -> str:
        """Selects a random quote from pool that hasn't been used yet in this game."""
        available = [q for q in pool if q not in used_set]
        if not available:
            # If all were used (e.g. 10+ checks at 0 Elo), reset and allow full pool
            available = list(pool)
        chosen = random.choice(available)
        used_set.add(chosen)
        return chosen

    def _process_state(
        self,
        game_id: str,
        engine: PanicEngine,
        moves: list[str],
        state: dict,
        is_white: bool,
        triggered_easter_eggs: set[str],
        used_quotes: set[str]
    ):
        """Processes current board state, checks, panic calculation, and move dispatch."""
        new_check, total_checks, current_elo = engine.analyze_moves_and_count_checks(moves)

        # Easter Egg: 1. e4 e5 2. Nf3 Nc6 3. Bc4 (Italian Game) as Black
        if not is_white and moves == ["e2e4", "e7e5", "g1f3", "b8c6", "f1c4"]:
            if "italian_f7" not in triggered_easter_eggs:
                triggered_easter_eggs.add("italian_f7")
                self.send_chat(game_id, "Take on f7. I dare you.")

        # Broadcast panic update if a new check occurred
        if new_check:
            if current_elo <= 600:
                quote = self._get_unique_quote(POTATO_FISH_PHRASES, used_quotes)
                if current_elo <= config.MIN_ELO:
                    self.send_chat(game_id, f"{quote} (0 elo)")
                else:
                    self.send_chat(game_id, f"{quote} 🐟 (-300 elo) (Rating: {current_elo} elo)")
            elif current_elo >= 2100:
                quote = self._get_unique_quote(CONFIDENT_FISH_PHRASES, used_quotes)
                self.send_chat(game_id, f"{quote} (Rating: {current_elo} elo)")
            else:
                quote = self._get_unique_quote(SCARED_FISH_PHRASES, used_quotes)
                self.send_chat(game_id, f"{quote} (Rating: {current_elo} elo)")

        # Reconstruct current board state
        board = chess.Board()
        for uci_str in moves:
            try:
                board.push_uci(uci_str)
            except ValueError:
                break

        if board.is_game_over():
            return

        bot_turn = (board.turn == chess.WHITE and is_white) or (board.turn == chess.BLACK and not is_white)
        if not bot_turn:
            return

        # Calculate time limit based on clock
        time_key = "wtime" if is_white else "btime"
        inc_key = "winc" if is_white else "binc"
        remaining_sec = parse_time_seconds(state.get(time_key), 60.0)
        inc_sec = parse_time_seconds(state.get(inc_key), 0.0)

        # Dynamic time allocation (safely handle numbers)
        time_limit_sec = max(0.1, min((remaining_sec / 30.0) + (inc_sec / 2.0), 2.0))

        # Ask PanicEngine for the next move
        move = engine.choose_move(board, time_limit=time_limit_sec)
        if move:
            move_uci = move.uci()
            logger.info(f"Playing move {move_uci} (Rating: {current_elo} Elo, Checks: {total_checks})")
            for attempt in range(1, 5):
                try:
                    self.client.bots.make_move(game_id, move_uci)
                    break
                except Exception as e:
                    logger.warning(f"Error submitting move {move_uci} (attempt {attempt}/4): {e}")
                    if attempt < 4:
                        time.sleep(0.5 * attempt)

    def run(self):
        """Main event listener loop streaming incoming challenges and games."""
        if not self.verify_account():
            sys.exit(1)

        logger.info("==================================================")
        logger.info("  Panic Fish Bot is ONLINE and waiting for games!")
        logger.info(f"  Rules: Starting Elo: {config.STARTING_ELO} | Drop: -{config.ELO_DROP_PER_CHECK}/check")
        logger.info("==================================================")

        backoff = 1
        while True:
            try:
                for event in self.client.bots.stream_incoming_events():
                    backoff = 1  # Reset backoff upon receiving events
                    event_type = event.get("type")

                    if event_type == "challenge":
                        challenge = event.get("challenge", {})
                        challenge_id = challenge.get("id")
                        challenger_info = challenge.get("challenger", {})
                        challenger = challenger_info.get("name", "Unknown")
                        challenger_title = challenger_info.get("title")

                        # 0. Block Bot-vs-Bot challenges
                        if challenger_title == "BOT":
                            logger.info(f"Declining challenge from {challenger}: Bot-vs-Bot challenges are disabled.")
                            try:
                                self.client.bots.decline_challenge(challenge_id, reason="nobot")
                            except Exception:
                                pass
                            continue

                        variant_info = challenge.get("variant", {})
                        variant_key = variant_info.get("key", "").lower()
                        initial_fen = challenge.get("initialFen")
                        time_control = challenge.get("timeControl", {})
                        tc_type = time_control.get("type", "").lower()
                        limit_sec = time_control.get("limit", 0)
                        increment_sec = time_control.get("increment", 0)

                        with self.active_games_lock:
                            busy = len(self.active_games) >= config.MAX_CONCURRENT_GAMES

                        if busy:
                            logger.info(f"Declining challenge from {challenger}: Bot is already in a game.")
                            try:
                                self.client.bots.decline_challenge(challenge_id, reason="later")
                            except Exception:
                                pass
                            continue

                        # 1. Enforce ONLY standard chess (no custom variants, no "from position")
                        if variant_key != "standard" or initial_fen:
                            logger.info(f"Declining challenge from {challenger}: Only standard chess allowed (no custom variants or from position).")
                            try:
                                self.client.bots.decline_challenge(challenge_id, reason="variant")
                            except Exception:
                                pass
                            continue

                        # 2. Enforce real-time clock (no correspondence or unlimited)
                        if tc_type != "clock":
                            logger.info(f"Declining challenge from {challenger}: Only real-time clock games allowed.")
                            try:
                                self.client.bots.decline_challenge(challenge_id, reason="timeControl")
                            except Exception:
                                pass
                            continue

                        # 3. Enforce maximum time control: 30+20 or lower (limit <= 1800s and increment <= 20s)
                        if limit_sec > 1800 or increment_sec > 20:
                            logger.info(f"Declining challenge from {challenger}: Time control ({limit_sec}s + {increment_sec}s) exceeds 30+20 max.")
                            try:
                                self.client.bots.decline_challenge(challenge_id, reason="tooSlow")
                            except Exception:
                                pass
                            continue

                        # Accept valid challenge
                        logger.info(f"Accepting challenge {challenge_id} from {challenger} (TimeControl: {limit_sec}+{increment_sec})")
                        try:
                            self.client.bots.accept_challenge(challenge_id)
                        except Exception as e:
                            logger.error(f"Failed to accept challenge: {e}")

                    elif event_type == "gameStart":
                        game = event.get("game", {})
                        game_id = game.get("id") or game.get("gameId")
                        if game_id:
                            with self.active_games_lock:
                                if game_id in self.active_games:
                                    continue
                                self.active_games.add(game_id)
                            t = threading.Thread(target=self.handle_game, args=(game_id,), daemon=True)
                            t.start()

                    elif event_type == "gameFinish":
                        game = event.get("game", {})
                        game_id = game.get("id") or game.get("gameId")
                        if game_id:
                            with self.active_games_lock:
                                self.active_games.discard(game_id)
                        logger.info(f"Game {game_id} marked as finished.")

            except Exception as e:
                logger.warning(f"Connection lost to Lichess events stream ({e}). Reconnecting in {backoff}s...")
                time.sleep(backoff)
                backoff = min(backoff * 2, 30)


if __name__ == "__main__":
    bot = PanicFishBot()
    bot.run()
