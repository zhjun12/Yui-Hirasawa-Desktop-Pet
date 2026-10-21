import unittest
from music_mode import MusicModeState


class MusicModeTests(unittest.TestCase):
    def test_open_once_and_pause_or_session_loss_does_not_exit(self):
        state=MusicModeState()
        self.assertEqual(state.observe(0,True,True),'enter')
        state.enter(cloud=True)
        for now in (1,20,100): self.assertIsNone(state.observe(now,True,True))
        self.assertTrue(state.active)

    def test_manual_exit_suppresses_until_confirmed_client_exit(self):
        state=MusicModeState();state.observe(0,True,True);state.enter(True);state.leave()
        self.assertIsNone(state.observe(10,True,True))
        state.observe(11,False,True)
        self.assertIsNone(state.observe(18,False,True))
        state.observe(19,False,True)
        self.assertEqual(state.observe(20,True,True),'enter')

    def test_real_exit_waits_eight_seconds(self):
        state=MusicModeState();state.observe(0,True,True);state.enter(True)
        self.assertIsNone(state.observe(1,False,True))
        self.assertIsNone(state.observe(8,False,True))
        self.assertEqual(state.observe(9,False,True),'exit')

    def test_unknown_presence_cancels_exit_confirmation(self):
        state=MusicModeState();state.observe(0,True,True);state.enter(True)
        state.observe(1,False,True);state.observe(20,None,True)
        self.assertIsNone(state.observe(21,False,True))

    def test_local_playback_is_offered_instead_of_replaced(self):
        state=MusicModeState()
        self.assertEqual(state.observe(0,True,True,True),'offer')
        self.assertFalse(state.active);self.assertTrue(state.offered)
        self.assertIsNone(state.observe(1,True,True,True))

    def test_client_exit_keeps_local_music_view(self):
        state=MusicModeState();state.observe(0,True,True);state.enter(False)
        state.observe(1,False,True)
        self.assertIsNone(state.observe(10,False,True));self.assertTrue(state.active)

    def test_auto_mode_can_be_disabled(self):
        state=MusicModeState()
        self.assertIsNone(state.observe(0,True,False))
        self.assertFalse(state.active)
