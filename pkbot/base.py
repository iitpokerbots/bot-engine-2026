'''
This file contains the base class that you should implement for your pokerbot.
'''
from .actions import ActionFold, ActionCall, ActionCheck, ActionRaise, ActionBid
from .states import GameInfo, PokerState


class BaseBot():
    '''
    The base class for a pokerbot.
    '''

    def on_hand_start(self, game_info: GameInfo, current_state: PokerState) -> None:
        '''
        Called when a new round starts. Called NUM_ROUNDS times.

        Arguments:
        game_info: the GameInfo object.
        current_state: the PokerState object.

        Returns:
        Nothing.
        '''
        raise NotImplementedError('on_hand_start')

    def on_hand_end(self, game_info: GameInfo, current_state: PokerState) -> None:
        '''
        Called when a round ends. Called NUM_ROUNDS times.

        Arguments:
        game_info: the GameInfo object.
        current_state: the PokerState object.

        Returns:
        Nothing.
        '''
        raise NotImplementedError('on_hand_end')

    def get_move(self, game_info: GameInfo, current_state: PokerState) -> ActionFold | ActionCall | ActionCheck | ActionRaise | ActionBid:
        '''
        Where the magic happens - your code should implement this function.
        Called any time the engine needs an action from your bot.

        Arguments:
        game_info: the GameInfo object.
        current_state: the PokerState object.

        Returns:
        Your action.
        '''
        # raise NotImplementedError('get_move')
        print(current_state.street)
        if current_state.street == 'auction':
            return ActionBid(2)
        elif ActionCall in current_state.valid_actions:
            return ActionCall()

        elif ActionCheck in current_state.valid_actions:
            return ActionCheck()
        else:
            return ActionFold()