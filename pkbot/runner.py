'''
The infrastructure for interacting with the engine.
'''
import argparse
import socket
from .actions import ActionBid, ActionFold, ActionCall, ActionCheck, ActionRaise
from .states import GameInfo, HandResult, GameState, PokerState
from .states import STARTING_STACK, BIG_BLIND, SMALL_BLIND
from .base import BaseBot


class Runner():
    '''
    Interacts with the engine.
    '''

    def __init__(self, pokerbot, socketfile):
        self.pokerbot = pokerbot
        self.socketfile = socketfile

    def receive(self):
        '''
        Generator for incoming messages from the engine.
        '''
        while True:
            packet = self.socketfile.readline().strip().split(' ')
            if not packet:
                break
            yield packet

    def send(self, action):
        '''
        Encodes an action and sends it to the engine.
        '''
        if isinstance(action, ActionFold):
            code = 'F'
        elif isinstance(action, ActionCall):
            code = 'C'
        elif isinstance(action, ActionCheck):
            code = 'K'
        elif isinstance(action, ActionBid): 
            code = 'A' + str(action.amount)
        else:  # isinstance(action, ActionRaise)
            code = 'R' + str(action.amount)
        self.socketfile.write(code + '\n')
        self.socketfile.flush()

    def run(self):
        '''
        Reconstructs the game tree based on the action history received from the engine.
        '''
        game_info = GameInfo(0, 0., 1)
        state: GameState = None
        active = 0
        round_flag = True
        for packet in self.receive():
            for clause in packet:
                if clause[0] == 'T':
                    game_info = GameInfo(game_info.bankroll, float(clause[1:]), game_info.round_num)
                elif clause[0] == 'P':
                    active = int(clause[1:])
                elif clause[0] == 'H':
                    hands = [[], []]
                    hands[active] = clause[1:].split(',')
                    wagers = [SMALL_BLIND, BIG_BLIND]
                    chips = [STARTING_STACK - SMALL_BLIND, STARTING_STACK - BIG_BLIND]
                    state = GameState(0, 0, False, [None, None], wagers, chips, hands, [[], []], [], None)
                    if round_flag:
                        self.pokerbot.on_hand_start(game_info, PokerState(state, active))
                        round_flag = False
                elif clause[0] == 'F':
                    state = state.apply_action(ActionFold())
                elif clause[0] == 'C':
                    state = state.apply_action(ActionCall())
                elif clause[0] == 'K':
                    state = state.apply_action(ActionCheck())
                elif clause[0] == 'R':
                    state = state.apply_action(ActionRaise(int(clause[1:])))
                elif clause[0] == 'A': 
                    state = state.apply_action(ActionBid(int(clause[1:])))
                elif clause[0] == 'N':
                    hands = [[], []]
                    chips, bids, opp_hands = clause[1:].split('_')
                    bids = [int(x) for x in bids.split(',')]
                    chips = [int(x) for x in chips.split(',')]
                    hands[active] = [card for card in opp_hands.split(',') if card != '']
                    state = GameState(state.dealer, state.street, state.auction, bids, state.wagers, chips, state.hands, hands, state.community_cards, state)
                elif clause[0] == 'B':
                    state = GameState(state.dealer, state.street, state.auction, state.bids, state.wagers, state.chips,
                                             state.hands, state.opp_hands, clause[1:].split(','), state.parent_state)
                elif clause[0] == 'O':
                    # backtrack
                    state = state.parent_state
                    revised_hands = list(state.hands)
                    revised_hands[1-active] = clause[1:].split(',')
                    revised_opp_hands = list(state.opp_hands)
                    revised_opp_hands[active] = clause[1:].split(',')
                    # rebuild history
                    state = GameState(state.dealer, state.street, state.auction, state.bids, state.wagers, state.chips,
                                             revised_hands, revised_opp_hands, state.community_cards, state.parent_state)
                    state = HandResult([0, 0], state.bids, state)
                elif clause[0] == 'D':
                    assert isinstance(state, HandResult)
                    delta = int(clause[1:])
                    payoffs = [-delta, -delta]
                    payoffs[active] = delta
                    state = HandResult(payoffs, state.bids, state.parent_state)
                    game_info = GameInfo(game_info.bankroll + delta, game_info.time_bank, game_info.round_num)
                    self.pokerbot.on_hand_end(game_info, PokerState(state, active))
                    game_info = GameInfo(game_info.bankroll, game_info.time_bank, game_info.round_num + 1)
                    round_flag = True
                elif clause[0] == 'Q':
                    return
            if round_flag:  # ack the engine
                self.send(ActionCheck())
            else:
                assert active == state.dealer % 2
                action = self.pokerbot.get_move(game_info, PokerState(state, active))
                self.send(action)

def parse_args():
    '''
    Parses arguments corresponding to socket connection information.
    '''
    parser = argparse.ArgumentParser(prog='python3 player.py')
    parser.add_argument('--host', type=str, default='localhost', help='Host to connect to, defaults to localhost')
    parser.add_argument('port', type=int, help='Port on host to connect to')
    return parser.parse_args()

def run_bot(pokerbot, args):
    '''
    Runs the pokerbot.
    '''
    assert isinstance(pokerbot, BaseBot)
    try:
        sock = socket.create_connection((args.host, args.port))
    except OSError:
        print('Could not connect to {}:{}'.format(args.host, args.port))
        return
    socketfile = sock.makefile('rw')
    runner = Runner(pokerbot, socketfile)
    runner.run()
    socketfile.close()
    sock.close()