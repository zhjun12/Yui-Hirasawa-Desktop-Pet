import unittest
from types import SimpleNamespace
from core import Animation


class Predictable:
    def __init__(self, preferred='roll'):
        self.preferred=preferred
    def uniform(self,low,high): return (low+high)/2
    def randint(self,low,high): return low
    def choices(self,items,weights):
        return [self.preferred if self.preferred in items else items[0]]


class ScheduleTests(unittest.TestCase):
    def create(self, preferred='roll', start=1000):
        self.now=start
        self.a=Animation(lambda:self.now,Predictable(preferred))
        self.a.configure_actions({
            'roll':SimpleNamespace(weights={'daily':25},cycles=(1,2),cooldown=90,duration=1.4),
            'stretch':SimpleNamespace(weights={'daily':25},cycles=(2,3),cooldown=90,duration=55/30)})
        return self.a

    def music(self):
        self.a.playing=True
        self.a.state()
        self.now+=1
        self.assertEqual(self.a.state(),'listen')

    def test_entry_uses_own_clock_and_burst_ends_on_loop(self):
        a=self.create()
        self.assertEqual(a.state(),'idle')
        self.now=1044.99
        self.assertEqual(a.state(),'idle')
        self.now=1045
        self.assertEqual(a.state(),'roll')
        self.now+=1.39
        self.assertEqual(a.state(),'roll')
        self.now+=.02
        self.assertEqual(a.state(),'idle')

    def test_music_does_not_switch_every_18_seconds(self):
        a=self.create('spin')
        self.music()
        self.now+=18
        self.assertEqual(a.state(),'listen')
        self.now+=49.5
        self.assertEqual(a.state(),'spin')
        self.now+=2.09
        self.assertEqual(a.state(),'spin')
        self.now+=.02
        self.assertEqual(a.state(),'listen')

    def test_pause_and_start_are_debounced(self):
        a=self.create()
        self.music()
        a.playing=False
        self.assertEqual(a.state(),'listen')
        self.now+=.4
        self.assertEqual(a.state(),'listen')
        a.playing=True
        self.assertEqual(a.state(),'listen')
        a.playing=False
        a.state()
        self.now+=1.21
        self.assertEqual(a.state(),'idle')

    def test_context_change_finishes_current_loop(self):
        a=self.create()
        a.state()
        self.now+=45
        self.assertEqual(a.state(),'roll')
        a.playing=True
        self.now+=.1
        a.state()
        self.now+=1
        self.assertEqual(a.state(),'roll')
        self.now+=.31
        self.assertEqual(a.state(),'listen')

    def test_focus_has_no_random_bursts(self):
        a=self.create()
        self.music()
        a.focus=True
        self.assertEqual(a.state(),'listen')
        self.now+=1000
        self.assertEqual(a.state(),'listen')
        a.playing=False
        a.state()
        self.now+=1.21
        self.assertEqual(a.state(),'idle')
        self.now+=1000
        self.assertEqual(a.state(),'idle')

    def test_interaction_resets_dwell_instead_of_replaying_old_burst(self):
        a=self.create()
        a.state()
        self.now+=45
        self.assertEqual(a.state(),'roll')
        a.interact('eat',4.4)
        self.assertEqual(a.state(),'eat')
        self.now+=4.5
        self.assertEqual(a.state(),'idle')
        self.now+=29
        self.assertEqual(a.state(),'idle')

    def test_fixed_mode_is_not_randomly_replaced(self):
        a=self.create()
        a.mode='stretch'
        self.assertEqual(a.state(),'stretch')
        self.now+=1000
        self.assertEqual(a.state(),'stretch')
        a.interact('eat',4.4)
        self.assertEqual(a.state(),'eat')
        self.now+=5
        self.assertEqual(a.state(),'stretch')

    def test_hidden_does_not_queue_overdue_random_actions(self):
        a=self.create()
        a.state()
        a.set_suspended(True)
        self.now+=1000
        self.assertEqual(a.state(),'idle')
        a.set_suspended(False)
        self.assertEqual(a.state(),'idle')
        self.now+=29
        self.assertEqual(a.state(),'idle')

    def test_cooldown_prevents_immediate_repeat(self):
        a=self.create()
        a.state()
        self.now+=45
        self.assertEqual(a.state(),'roll')
        self.now+=1.41
        self.assertEqual(a.state(),'idle')
        self.now+=45
        self.assertNotEqual(a.state(),'roll')


if __name__=='__main__': unittest.main()
