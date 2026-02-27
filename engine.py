'''
1.0.0 IIT-POKERBOTS GAME ENGINE
DO NOT REMOVE, RENAME, OR EDIT THIS FILE
'''
from collections import namedtuple
import eval7
import argparse
import json
import os
from queue import Queue
import subprocess
import socket
import sys
from threading import Thread
import time
from datetime import datetime
import traceback
import random

sys.path.append(os.getcwd())

from config import *

PLAYER_LOG_SIZE_LIMIT = 524288

GAME_CLOCK = 30.0
BUILD_TIMEOUT = 10.0
CONNECT_TIMEOUT = 10.0

NUM_ROUNDS = 1000
STARTING_STACK = 5000
BIG_BLIND = 20
SMALL_BLIND = 10

# Format Utils ---------------------------------------------------------------------------------------
CCARDS = lambda cards: ','.join(map(str, cards))
PCARDS = lambda cards: '[{}]'.format(' '.join(map(str, cards)))
PVALUE = lambda name, value: ', {} ({})'.format(name, value)
STATUS = lambda players: ''.join([PVALUE(p.name, p.bankroll) for p in players])
STREET_LABELS = ['Flop', 'Turn', 'River']

# Actions --------------------------------------------------------------------------------------------
ActionFold = namedtuple('ActionFold', [])
ActionCall = namedtuple('ActionCall', [])
ActionCheck = namedtuple('ActionCheck', [])
ActionRaise = namedtuple('ActionRaise', ['amount'])
ActionBid = namedtuple('ActionBid', ['amount'])

DECODE_ACTION = {
    'F': ActionFold,
    'C': ActionCall,
    'K': ActionCheck,
    'R': ActionRaise,
    'A': ActionBid,
}

# States ---------------------------------------------------------------------------------------------
HandResult = namedtuple('HandResult', ['payoffs', 'bids', 'parent_state'])

class GameState(
            namedtuple(
                '_GameState',
                ['dealer', 'street', 'auction', 'bids', 'wagers', 'chips', 'hands', 'opp_hands', 'deck', 'parent_state']
            )
    ):
    '''Represents the state of the table at a specific point in the hand.'''

    def calculate_result(self):
        '''Determines the winner and calculates the chip transfer.'''
        score0 = eval7.evaluate(self.deck.peek(5) + self.hands[0])
        score1 = eval7.evaluate(self.deck.peek(5) + self.hands[1])
        if score0 > score1:
            delta = STARTING_STACK - self.chips[1]
        elif score0 < score1:
            delta = self.chips[0] - STARTING_STACK
        else:  # equal split the pot
            delta = (self.chips[0] - self.chips[1]) // 2
        return HandResult([delta, -delta], self.auction, self)

    def get_valid_actions(self):
        '''Returns the set of actions available to the current player.'''
        if self.auction:
            return {ActionBid}

        active_idx = self.dealer % 2
        cost_to_call = self.wagers[1-active_idx] - self.wagers[active_idx]
        
        if cost_to_call == 0:
            # Check or Raise allowed, unless all-in
            cannot_bet = (self.chips[0] == 0 or self.chips[1] == 0)
            return {ActionCheck} if cannot_bet else {ActionCheck, ActionRaise}
        
        # Must Call or Fold (or Raise if possible)
        cannot_raise = (cost_to_call == self.chips[active_idx] or self.chips[1-active_idx] == 0)
        return {ActionFold, ActionCall} if cannot_raise else {ActionFold, ActionCall, ActionRaise}

    def get_raise_limits(self):
        '''
        Returns (min_raise, max_raise) for the active player.
        '''
        active_idx = self.dealer % 2
        cost = self.wagers[1-active_idx] - self.wagers[active_idx]
        max_bet = min(self.chips[active_idx], self.chips[1-active_idx] + cost)
        min_bet = min(max_bet, cost + max(cost, BIG_BLIND))
        return (self.wagers[active_idx] + min_bet, self.wagers[active_idx] + max_bet)

    def get_bid_limits(self):
        '''
        Returns (min_bid, max_bid) for the active player.
        '''
        active_idx = self.dealer % 2
        max_bid = self.chips[active_idx]
        min_bid = 0
        return (min_bid, max_bid)
    
    def next_street(self):
        '''
        Moves the game to the next betting round or showdown.
        '''
        if self.street == 5:
            return self.calculate_result()
        if self.street == 0:
            return GameState(1, 3, True, self.bids, [0, 0], self.chips, self.hands, self.opp_hands, self.deck, self)
        # new_street = 3 if self.street == 0 else self.street + 1
        return GameState(1, self.street+1, False, self.bids, [0, 0], self.chips, self.hands, self.opp_hands, self.deck, self)
    
    def apply_action(self, action):
        '''
        Transitions the state based on the action taken.
        '''
        active = self.dealer % 2
        
        if isinstance(action, ActionFold):
            delta = self.chips[0] - STARTING_STACK if active == 0 else STARTING_STACK - self.chips[1]
            return HandResult([delta, -delta], self.bids, self)
            
        if isinstance(action, ActionCall):
            if self.dealer == 0:  # SB calls BB
                return GameState(1, 0, self.auction, self.bids, [BIG_BLIND] * 2, [STARTING_STACK - BIG_BLIND] * 2, self.hands, self.opp_hands, self.deck, self)
            
            # Match the bet
            next_wagers = list(self.wagers)
            next_chips = list(self.chips)
            amt_to_call = next_wagers[1-active] - next_wagers[active]
            next_chips[active] -= amt_to_call
            next_wagers[active] += amt_to_call
            
            state = GameState(self.dealer + 1, self.street, self.auction, self.bids, next_wagers, next_chips, self.hands, self.opp_hands, self.deck, self)
            return state.next_street()
            
        if isinstance(action, ActionCheck):
            if (self.street == 0 and self.dealer > 0) or self.dealer > 1:
                return self.next_street()
            return GameState(self.dealer + 1, self.street, self.auction, self.bids, self.wagers, self.chips, self.hands, self.opp_hands, self.deck, self)
        
        if isinstance(action, ActionBid):
            self.bids[active] = action.amount

            if None not in self.bids: 
                if self.bids[0] == self.bids[1]:
                    rv_card_0 = random.choice(self.hands[0])
                    rv_card_1 = random.choice(self.hands[1])
                    self.opp_hands[0].append(rv_card_1)
                    self.opp_hands[1].append(rv_card_0)

                    new_chips = list(self.chips)
                    new_chips[0] -= self.bids[0]
                    new_chips[1] -= self.bids[1]
                    state = GameState(1, self.street, False, self.bids, self.wagers, new_chips, self.hands, self.opp_hands, self.deck, self)

                else:
                    winner = self.bids.index(max(self.bids))
                    revealed_card = random.choice(self.hands[1 - winner])
                    self.opp_hands[winner].append(revealed_card)

                    new_chips = list(self.chips)
                    new_chips[winner] -= self.bids[1 - winner]
                    state = GameState(1, self.street, False, self.bids, self.wagers, new_chips, self.hands, self.opp_hands, self.deck, self)
                return state
            
            else:
                return GameState(self.dealer + 1, self.street, True, self.bids, self.wagers, self.chips, self.hands, self.opp_hands, self.deck, self)

        # ActionRaise
        next_wagers = list(self.wagers)
        next_chips = list(self.chips)
        added = action.amount - next_wagers[active]
        next_chips[active] -= added
        next_wagers[active] += added
        return GameState(self.dealer + 1, self.street, self.auction, self.bids, next_wagers, next_chips, self.hands, self.opp_hands, self.deck, self)


# BotWrapper --------------------------------------------------------------------------------------
class BotProcess:
    '''
    Manages the subprocess and socket connection for a single bot.
    '''

    def __init__(self, name, file_path):
        self.name = name
        self.file_path = file_path
        self.time_bank = GAME_CLOCK
        self.bankroll = 0
        self.proc = None
        self.socketfile = None
        self.bytes_queue = Queue()
        self.query_times = []
        self.hand_response_times = {}
        self.wins = 0
        self.auction_wins = 0
        self.auction_total = 0
        self.bids = []

    def run(self):
        '''
        Runs the pokerbot and establishes the socket connection.
        '''
        try:
            server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            with server_socket:
                server_socket.bind(('', 0))
                server_socket.settimeout(CONNECT_TIMEOUT)
                server_socket.listen()
                port = server_socket.getsockname()[1]

                proc = subprocess.Popen(
                    [PYTHON_CMD, self.file_path, str(port)],
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    cwd=os.path.dirname(self.file_path))
                self.proc = proc
                # function for bot listening
                def enqueue_output(out, queue):
                    try:
                        for line in out:
                            queue.put(line)
                    except ValueError:
                        pass
                # start a separate bot listening thread which dies with the program
                Thread(target=enqueue_output, args=(proc.stdout, self.bytes_queue), daemon=True).start()
                # block until we timeout or the player connects
                client_socket, _ = server_socket.accept()
                with client_socket:
                    client_socket.settimeout(CONNECT_TIMEOUT)
                    sock = client_socket.makefile('rw')
                    self.socketfile = sock
                    print(self.name, 'connected successfully')
        except (TypeError, ValueError):
            print(self.name, 'run command misformatted')
        except OSError as e:
            print(self.name, ' timed out or failed to connect.')
            self.bytes_queue.put(traceback.format_exc().encode())
        except socket.timeout:
            print('Timed out waiting for', self.name, 'to connect')

    def stop(self):
        '''
        Closes the socket connection and stops the pokerbot.
        '''
        if self.socketfile is not None:
            try:
                self.socketfile.write('Q\n')
                self.socketfile.close()
            except socket.timeout:
                print('Timed out waiting for', self.name, 'to disconnect')
            except OSError:
                print('Could not close socket connection with', self.name)
        if self.proc is not None:
            try:
                outs, _ = self.proc.communicate(timeout=CONNECT_TIMEOUT)
                self.bytes_queue.put(outs)
            except subprocess.TimeoutExpired:
                print('Timed out waiting for', self.name, 'to quit')
                self.proc.kill()
                outs, _ = self.proc.communicate()
                self.bytes_queue.put(outs)
        os.makedirs(GAME_LOG_FOLDER, exist_ok=True)
        with open(os.path.join(GAME_LOG_FOLDER, self.name + '.plog'), 'wb') as log_file:
            bytes_written = 0
            for output in self.bytes_queue.queue:
                try:
                    bytes_written += log_file.write(output)
                    if bytes_written >= PLAYER_LOG_SIZE_LIMIT:
                        break
                except TypeError:
                    pass

    def query(self, state, player_message, game_log, round_num):
        '''
        Requests one action from the pokerbot over the socket connection.
        At the end of the round, we request a CheckAction from the pokerbot.
        '''
        valid_actions = state.get_valid_actions() if isinstance(state, GameState) else {ActionCheck}
        if self.socketfile is not None and self.time_bank > 0.:
            clause = ''
            try:
                player_message[0] = 'T{:.3f}'.format(self.time_bank)
                message = ' '.join(player_message) + '\n'
                del player_message[1:]  # do not send redundant action history
                start_time = time.perf_counter()
                self.socketfile.write(message)
                self.socketfile.flush()
                clause = self.socketfile.readline().strip()
                end_time = time.perf_counter()
                response_time = end_time - start_time
                self.time_bank -= response_time
                self.query_times.append(response_time)
                self.hand_response_times[round_num] = self.hand_response_times.get(round_num, 0) + response_time
                if self.time_bank <= 0.:
                    raise socket.timeout
                action = DECODE_ACTION[clause[0]]
                if action in valid_actions:
                    if clause[0] == 'R':
                        if '.' in clause[1:]:
                            game_log.append(self.name + ' attempted illegal ActionRaise({}) with decimal'.format(clause[1:]))
                            self.bytes_queue.put(f"[Round#{round_num}] Tried to raise with decimal amount: {clause[1:]}\n".encode())
                            return ActionCheck() if ActionCheck in valid_actions else ActionFold()
                        amount = int(clause[1:])
                        min_raise, max_raise = state.get_raise_limits()
                        if min_raise <= amount <= max_raise:
                            return action(amount)
                    elif clause[0] == 'A':
                        if '.' in clause[1:]:
                            game_log.append(self.name + ' attempted illegal bid with decimal')
                            self.bytes_queue.put(f"[Round#{round_num}] Tried to bid with decimal amount: {clause[1:]}\n".encode())
                            return ActionCheck() if ActionCheck in valid_actions else ActionFold()
                        amount = int(clause[1:])
                        min_bid, max_bid = state.get_bid_limits()
                        if min_bid <= amount <= max_bid:
                            return action(amount)
                    else:
                        return action()
                
                if clause[0] in ('R', 'A'):
                    game_log.append(self.name + ' attempted illegal ' + action.__name__ + ' with amount ' + str(int(clause[1:])))
                else:
                    game_log.append(self.name + ' attempted illegal ' + action.__name__)

            except socket.timeout:
                error_message = self.name + ' ran out of time'
                game_log.append(error_message)
                print(error_message)
                self.time_bank = 0.
            except OSError:
                error_message = self.name + ' disconnected'
                game_log.append(error_message)
                print(error_message)
                self.time_bank = 0.
            except (IndexError, KeyError, ValueError) as e:
                game_log.append(self.name + ' response misformatted: ' + str(clause))
        # set a base bid action of 0 if pokerbot fails to submit legal bid action
        if ActionBid in valid_actions: 
            return ActionBid(0)
        
        return ActionCheck() if ActionCheck in valid_actions else ActionFold()

# PokerMatch -------------------------------------------------------------------------------------------------
class PokerMatch():
    '''Manages logging and the high-level game procedure.'''

    def __init__(self, small_log=False):
        self.small_log = small_log
        self.timestamp = datetime.now()
        self.log = [self.timestamp.strftime('%Y-%m-%d %H:%M:%S ') + BOT_1_NAME + ' vs ' + BOT_2_NAME]
        self.player_messages = [[], []]

    def log_state(self, players, state: GameState):
        '''
        Incorporates GameState information into the game log and player messages.
        '''
        if state.street == 3 and state.auction is False and state.dealer == 1:
            for i in range(2):
                if len(state.opp_hands[i]) == 1:
                    self.log.append('{} won the auction and was revealed {}'.format(players[i].name, PCARDS(state.opp_hands[i])))
            
            self.player_messages[0].append('P0')
            self.player_messages[0].append('N' + ','.join([str(x) for x in state.chips]) + '_' + ','.join([str(x) for x in state.bids]) + '_' + CCARDS(state.opp_hands[0]))
            self.player_messages[1].append('P1')
            self.player_messages[1].append('N' + ','.join([str(x) for x in state.chips]) + '_' + ','.join([str(x) for x in state.bids]) + '_' + CCARDS(state.opp_hands[1]))

    
        if state.street == 0 and state.dealer == 0:
            if not self.small_log:
                self.log.append('{} posts blind: {}'.format(players[0].name, SMALL_BLIND))
                self.log.append('{} posts blind: {}'.format(players[1].name, BIG_BLIND))
                self.log.append('{} received {}'.format(players[0].name, PCARDS(state.hands[0])))
                self.log.append('{} received {}'.format(players[1].name, PCARDS(state.hands[1])))
            else:
                self.log.append('{}: {}'.format(players[0].name, PCARDS(state.hands[0])))
                self.log.append('{}: {}'.format(players[1].name, PCARDS(state.hands[1])))
            self.player_messages[0] = ['T0.', 'P0', 'H' + CCARDS(state.hands[0])]
            self.player_messages[1] = ['T0.', 'P1', 'H' + CCARDS(state.hands[1])]
        elif state.street > 0 and state.dealer == 1:
            board = state.deck.peek(state.street)
            self.log.append(STREET_LABELS[state.street - 3] + ' ' + PCARDS(board) +
                            PVALUE(players[0].name, STARTING_STACK-state.chips[0]) +
                            PVALUE(players[1].name, STARTING_STACK-state.chips[1]))
            compressed_board = 'B' + CCARDS(board)
            self.player_messages[0].append(compressed_board)
            self.player_messages[1].append(compressed_board)

    def log_action(self, name, action, bet_override):
        '''
        Incorporates action information into the game log and player messages.
        '''
        if isinstance(action, ActionFold):
            phrasing = ' folds'
            code = 'F'
        elif isinstance(action, ActionCall):
            phrasing = ' calls'
            code = 'C'
        elif isinstance(action, ActionCheck):
            phrasing = ' checks'
            code = 'K'
        elif isinstance(action, ActionBid):
            phrasing = ' bids ' + str(action.amount)
            code = 'A' + str(action.amount)
        else:  # isinstance(action, ActionRaise)
            phrasing = (' bets ' if bet_override else ' raises to ') + str(action.amount)
            code = 'R' + str(action.amount)
        if self.small_log:
            self.log.append(name + ' ' + code)
        else:
            self.log.append(name + phrasing)
        self.player_messages[0].append(code)
        self.player_messages[1].append(code)

    def log_result(self, players, result):
        '''
        Incorporates HandResult information into the game log and player messages.
        '''
        prev = result.parent_state
        if prev.wagers[0] == prev.wagers[1]:
            self.log.append('{} shows {}'.format(players[0].name, PCARDS(prev.hands[0])))
            self.log.append('{} shows {}'.format(players[1].name, PCARDS(prev.hands[1])))
            self.player_messages[0].append('O' + CCARDS(prev.hands[1]))
            self.player_messages[1].append('O' + CCARDS(prev.hands[0]))
        if self.small_log:
            self.log.append('{}: {:+d}'.format(players[0].name, result.payoffs[0]))
            self.log.append('{}: {:+d}'.format(players[1].name, result.payoffs[1]))
        else:
            self.log.append('{} awarded {}'.format(players[0].name, result.payoffs[0]))
            self.log.append('{} awarded {}'.format(players[1].name, result.payoffs[1]))
        self.player_messages[0].append('D' + str(result.payoffs[0]))
        self.player_messages[1].append('D' + str(result.payoffs[1]))

    def play_hand(self, players, round_num):
        '''
        Runs one round of poker.
        '''
        deck = eval7.Deck()
        deck.shuffle()
        hands = [deck.deal(2), deck.deal(2)]
        wagers = [SMALL_BLIND, BIG_BLIND]
        chips = [STARTING_STACK - SMALL_BLIND, STARTING_STACK - BIG_BLIND]
        state = GameState(0, 0, False, [None, None], wagers, chips, hands, [[], []], deck, None)
        
        while not isinstance(state, HandResult):
            self.log_state(players, state)
            active = state.dealer % 2
            player = players[active]
            action = player.query(state, self.player_messages[active], self.log, round_num)
            bet_override = (state.wagers == [0, 0])
            self.log_action(player.name, action, bet_override)
            previous_auction = state.auction
            state = state.apply_action(action)
            if previous_auction and not isinstance(state, HandResult) and not state.auction:
                players[0].auction_total += 1
                players[1].auction_total += 1
                players[0].bids.append(state.bids[0])
                players[1].bids.append(state.bids[1])
                if state.bids[0] > state.bids[1]:
                    players[0].auction_wins += 1
                elif state.bids[1] > state.bids[0]:
                    players[1].auction_wins += 1
            
        self.log_result(players, state)
        for player, player_message, delta in zip(players, self.player_messages, state.payoffs):
            player.query(state, player_message, self.log, round_num)
            player.bankroll += delta
            if delta > 0:
                player.wins += 1

    def run(self):
        '''
        Runs one game of poker.
        '''
        start_time = time.perf_counter()
        if not self.small_log:
            print('██ ██ ████████     ██████   ██████  ██   ██ ███████ ██████  ██████   ██████  ████████ ███████ ')
            print('██ ██    ██        ██   ██ ██    ██ ██  ██  ██      ██   ██ ██   ██ ██    ██    ██    ██      ')
            print('██ ██    ██        ██████  ██    ██ █████   █████   ██████  ██████  ██    ██    ██    ███████ ')
            print('██ ██    ██        ██      ██    ██ ██  ██  ██      ██   ██ ██   ██ ██    ██    ██         ██ ')
            print('██ ██    ██        ██       ██████  ██   ██ ███████ ██   ██ ██████   ██████     ██    ███████ ')
            print()
        print('Initializing Game Engine...')
        players = [
            BotProcess(BOT_1_NAME, BOT_1_FILE),
            BotProcess(BOT_2_NAME, BOT_2_FILE)
        ]
        all_bots = list(players)
        for player in players:
            player.run()
        for round_num in range(1, NUM_ROUNDS + 1):
            self.log.append('')
            self.log.append('Round #' + str(round_num) + STATUS(players))
            self.play_hand(players, round_num)
            players = players[::-1]
        self.log.append('')
        self.log.append('Final' + STATUS(players))

        print("\n=== Game Stats ===")
        for bot in all_bots:
            print(f"\nStats for {bot.name}:")
            total_queries = len(bot.query_times)
            avg_query = sum(bot.query_times) / total_queries if total_queries > 0 else 0.0
            max_query = max(bot.query_times) if total_queries > 0 else 0.0
            avg_hand_time = sum(bot.hand_response_times.values()) / NUM_ROUNDS
            win_rate = bot.wins / NUM_ROUNDS
            avg_payoff = bot.bankroll / NUM_ROUNDS
            auction_rate = bot.auction_wins / bot.auction_total if bot.auction_total > 0 else 0.0
            
            if bot.bids:
                avg_bid = sum(bot.bids) / len(bot.bids)
                var_bid = sum((x - avg_bid) ** 2 for x in bot.bids) / len(bot.bids)
            else:
                avg_bid = 0.0
                var_bid = 0.0
            
            print(f"  Total Bankroll: {bot.bankroll}")
            print(f"------------------------------------------------------------")
            print(f"  Win Rate: {win_rate:.1%}")
            print(f"  Avg Payoff/Hand: {avg_payoff:.2f}")
            print(f"------------------------------------------------------------")
            print(f"  Auction Win Rate: {auction_rate:.1%}")
            print(f"  Avg Bid Amount (Mean, Var): ({avg_bid:.2f}, {var_bid:.2f})")
            print(f"------------------------------------------------------------")
            print(f"  Avg Response Time (Query): {avg_query:.5f}s")
            print(f"  Avg Response Time (Hand): {avg_hand_time:.5f}s")
            print(f"  Max Response Time: {max_query:.5f}s")

        print(f"\nTotal Match Time: {time.perf_counter() - start_time:.3f}s")
        for player in players:
            player.stop()

        name = f"{self.timestamp.strftime('%Y%m%d-%H%M%S-%f')}.glog"
        print('Writing game log to', name)
        os.makedirs(GAME_LOG_FOLDER, exist_ok=True)
        with open(os.path.join(GAME_LOG_FOLDER, name), 'w') as log_file:
            log_file.write('\n'.join(self.log))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--small_log', action='store_true', help='Use compressed logging format')
    args = parser.parse_args()
    PokerMatch(small_log=args.small_log).run()