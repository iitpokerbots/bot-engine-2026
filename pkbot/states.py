'''
Encapsulates game and round state information for the player.
'''
from collections import namedtuple
from .actions import ActionFold, ActionCall, ActionCheck, ActionRaise, ActionBid

GameInfo = namedtuple('GameInfo', ['bankroll', 'time_bank', 'round_num'])
HandResult = namedtuple('HandResult', ['payoffs', 'bids', 'parent_state'])

NUM_ROUNDS = 1000
STARTING_STACK = 5000
BIG_BLIND = 20
SMALL_BLIND = 10


class GameState(namedtuple('_GameState', ['dealer', 'street', 'auction', 'bids', 'wagers', 'chips', 'hands', 'opp_hands', 'community_cards', 'parent_state'])):
    '''
    Encodes the game tree for one round of poker.
    '''

    def get_street_name(self):
        '''
        Returns the name of the current street.
        '''
        if self.auction:
            return 'auction'
        return {
            0: 'pre-flop',
            3: 'flop',
            4: 'turn',
            5: 'river'
        }[self.street]

    def calculate_result(self):
        '''
        Compares the players' hands and computes payoffs.
        '''
        return HandResult([0, 0], self.bids, self)

    def get_valid_actions(self):
        '''
        Returns a set which corresponds to the active player's legal moves.
        '''
        if self.auction:
            return {ActionBid}
        active_idx = self.dealer % 2
        cost = self.wagers[1-active_idx] - self.wagers[active_idx]
        if cost == 0:
            # we can only raise the stakes if both players can afford it
            cannot_bet = (self.chips[0] == 0 or self.chips[1] == 0)
            return {ActionCheck} if cannot_bet else {ActionCheck, ActionRaise}
        # cost > 0
        # similarly, re-raising is only allowed if both players can afford it
        cannot_raise = (cost == self.chips[active_idx] or self.chips[1-active_idx] == 0)
        return {ActionFold, ActionCall} if cannot_raise else {ActionFold, ActionCall, ActionRaise}

    def get_raise_limits(self):
        '''
        Returns a tuple of the minimum and maximum legal raises.
        '''
        active_idx = self.dealer % 2
        cost = self.wagers[1-active_idx] - self.wagers[active_idx]
        max_bet = min(self.chips[active_idx], self.chips[1-active_idx] + cost)
        min_bet = min(max_bet, cost + max(cost, BIG_BLIND))
        return (self.wagers[active_idx] + min_bet, self.wagers[active_idx] + max_bet)

    def next_street(self):
        '''
        Resets the players' pips and advances the game tree to the next round of betting.
        '''
        if self.street == 5:
            return self.calculate_result()
        if self.street == 0:
            return GameState(1, 3, True, self.bids, [0, 0], self.chips, self.hands, self.opp_hands, self.community_cards, self)    
        return GameState(1, self.street+1, False, self.bids, [0, 0], self.chips, self.hands, self.opp_hands, self.community_cards, self)

    def apply_action(self, action):
        '''
        Advances the game tree by one action performed by the active player.
        '''
        active = self.dealer % 2
        if isinstance(action, ActionFold):
            delta = self.chips[0] - STARTING_STACK if active == 0 else STARTING_STACK - self.chips[1]
            return HandResult([delta, -delta], self.bids, self)
        if isinstance(action, ActionCall):
            if self.dealer == 0:  # sb calls bb
                return GameState(1, 0, self.auction, self.bids, [BIG_BLIND] * 2, [STARTING_STACK - BIG_BLIND] * 2, self.hands, self.opp_hands, self.community_cards, self)
            # match bet
            next_wagers = list(self.wagers)
            next_chips = list(self.chips)
            amt = next_wagers[1-active] - next_wagers[active]
            next_chips[active] -= amt
            next_wagers[active] += amt
            state = GameState(self.dealer + 1, self.street, self.auction, self.bids, next_wagers, next_chips, self.hands, self.opp_hands, self.community_cards, self)
            return state.next_street()
        if isinstance(action, ActionCheck):
            if (self.street == 0 and self.dealer > 0) or self.dealer > 1:  # both players acted
                return self.next_street()
            # check
            return GameState(self.dealer + 1, self.street, self.auction, self.bids, self.wagers, self.chips, self.hands, self.opp_hands, self.community_cards, self)
        
        if isinstance(action, ActionBid):
            self.bids[active] = -1
            if None not in self.bids: 
                if self.bids[0] == self.bids[1]:
                    state = GameState(1, self.street, False, self.bids, self.wagers, self.chips, self.hands, self.opp_hands, self.community_cards, self)

                else:
                    state = GameState(1, self.street, False, self.bids, self.wagers, self.chips, self.hands, self.opp_hands, self.community_cards, self)
                return state
            
            else:
                return GameState(self.dealer + 1, self.street, self.auction, self.bids, self.wagers, self.chips, self.hands, self.opp_hands, self.community_cards, self)
        # isinstance(action, ActionRaise)
        next_wagers = list(self.wagers)
        next_chips = list(self.chips)
        added = action.amount - next_wagers[active]
        next_chips[active] -= added
        next_wagers[active] += added
        return GameState(self.dealer + 1, self.street, self.auction, self.bids, next_wagers, next_chips, self.hands, self.opp_hands, self.community_cards, self)


class PokerState:
    '''
    A wrapper around GameState to provide cleaner access to game information.
    '''
    is_terminal: bool
    street: str
    my_hand: list[str]
    board: list[str]
    opp_revealed_cards: list[str]
    my_chips: int
    opp_chips: int
    my_wager: int
    opp_wager: int
    pot: int
    cost_to_call: int
    is_bb: bool
    legal_actions: set
    payoff: int
    raise_bounds: tuple[int, int]

    def __init__(self, state, active):
        self.is_terminal = isinstance(state, HandResult)
        # If terminal, we look at the parent state for the board/hands info
        current_state = state.parent_state if self.is_terminal else state

        self.street = current_state.get_street_name() # 'Pre-Flop', 'Flop', 'Auction', 'Turn', or 'River'
        self.my_hand = current_state.hands[active]
        self.board = current_state.community_cards
        self.opp_revealed_cards = current_state.opp_hands[active]
        
        self.my_chips = current_state.chips[active]
        self.opp_chips = current_state.chips[1-active]
        self.my_wager = current_state.wagers[active]
        self.opp_wager = current_state.wagers[1-active]
        
        self.pot = (STARTING_STACK - self.my_chips) + (STARTING_STACK - self.opp_chips)
        self.cost_to_call = self.opp_wager - self.my_wager
        self.is_bb = active == 1
        
        if self.is_terminal:
            self.legal_actions = set()
            self.payoff = state.payoffs[active]
            self.raise_bounds = (0, 0)
        else:
            self.legal_actions = current_state.get_valid_actions()
            self.payoff = 0
            self.raise_bounds = current_state.get_raise_limits()

    def can_act(self, action_cls):
        '''Checks if a specific action class is currently legal.'''
        return action_cls in self.legal_actions