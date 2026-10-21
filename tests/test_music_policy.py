import copy
import random
import unittest
from pathlib import Path
from types import SimpleNamespace

from core import Animation
from music_policy import MusicIntensity,load_music_policy,validate_music_policy

ROOT=Path(__file__).resolve().parents[1]
POLICY=load_music_policy(ROOT/'assets/music-policy.json')


def schedule(seed=42,missing=()):
    now=[0.]
    a=Animation(lambda:now[0],random.Random(seed))
    packs={key:SimpleNamespace(weights={'daily':25,'music':1},cycles=(1,2),cooldown=90,duration=duration)
           for key,duration in [('sing_guitar',2.436),('roll',1.3346588283),('stretch',1.8333271344)]
           if key not in missing}
    a.configure_actions(packs)
    a.configure_music(POLICY)
    return a,now


def simulate(a,now,seconds=3600):
    a.playing=True
    a.state();now[0]=1.01;a.state()
    end=now[0]+seconds
    while now[0]<end:
        now[0]=min(a._deadline,end)
        a.state()
    total=sum(a.music_spent.values())
    return {key:value/total*100 for key,value in a.music_spent.items()}


class MusicPolicyTests(unittest.TestCase):
    def test_long_term_time_shares_across_random_durations(self):
        for seed in (1,42,123):
            a,now=schedule(seed)
            actual=simulate(a,now)
            for key,rule in POLICY['actions'].items():
                self.assertLess(abs(actual[key]-rule['share']),1.,(seed,key,actual))

    def test_integer_loops_cooldowns_and_no_consecutive_repeat(self):
        a,now=schedule()
        a.playing=True;a.state();now[0]=1.01
        previous=None;ends={}
        for _ in range(180):
            state=a.state();rule=POLICY['actions'][state]
            if not POLICY.get('allow_repeat'):
                self.assertNotEqual(state,previous)
            if state in ends:
                self.assertGreaterEqual(now[0]+1e-8,ends[state]+rule['cooldown_seconds'])
            duration=a._deadline-now[0]
            if 'cycles' in rule:
                loops=duration/a.loop_seconds[state]
                self.assertAlmostEqual(loops,round(loops),places=6)
                self.assertGreaterEqual(round(loops),rule['cycles'][0])
                self.assertLessEqual(round(loops),rule['cycles'][1])
            else:
                self.assertGreaterEqual(duration+1e-8,rule['hold_seconds'][0])
                self.assertLessEqual(duration,rule['hold_seconds'][1]+1e-8)
            previous=state;ends[state]=a._deadline;now[0]=a._deadline

    def test_pause_finishes_only_current_loop_and_returns_daily(self):
        a,now=schedule()
        a.playing=True;a.state();now[0]=1.01;a.state()
        a._music_last_choice=None
        a.music_spent.clear()
        a.music_spent.update({'listen':10000,'spin':10000,'roll':10000,'stretch':10000})
        a._music_next(now[0])
        self.assertEqual(a.state(),'sing_guitar')
        now[0]+=.1;a.playing=False;a.state()
        now[0]+=1.21
        self.assertEqual(a.state(),'sing_guitar')
        now[0]=a._pending[1]
        self.assertEqual(a.state(),'idle')

    def test_interaction_time_is_excluded_and_resume_is_immediate(self):
        a,now=schedule();a.playing=True;a.state();now[0]=1.01;a.state()
        now[0]+=.5;a.interact('eat',4.4)
        before=sum(a.music_spent.values())
        self.assertEqual(a.state(),'eat')
        now[0]+=200
        self.assertIn(a.state(),POLICY['actions'])
        self.assertAlmostEqual(sum(a.music_spent.values()),before)
        self.assertLessEqual(a._deadline-now[0],75)

    def test_focus_hidden_and_fixed_modes_do_not_accumulate_music_time(self):
        for mode in ('focus','hidden','fixed'):
            a,now=schedule();a.playing=True;a.state();now[0]=1.01;a.state()
            now[0]+=.4
            if mode=='focus': a.focus=True
            elif mode=='hidden': a.set_suspended(True)
            else: a.mode='stretch'
            a.state();before=sum(a.music_spent.values())
            now[0]+=1000
            self.assertEqual(a.state(),'stretch' if mode=='fixed' else 'listen')
            self.assertAlmostEqual(sum(a.music_spent.values()),before)

    def test_missing_pack_renormalizes_remaining_time_shares(self):
        a,now=schedule(missing={'sing_guitar'})
        # Isolate normalization from the shared cooldown's intentional time cap.
        policy=copy.deepcopy(POLICY)
        for rule in policy['actions'].values():
            rule['cooldown_seconds']=0
        a.configure_music(policy)
        actual=simulate(a,now,10800)
        self.assertNotIn('sing_guitar',actual)
        for key,percent in actual.items():
            self.assertLess(abs(percent-POLICY['actions'][key]['share']/55*100),1.)

    def test_follow_music_can_be_disabled(self):
        a,now=schedule();a.playing=True;a.follow_music=False
        a.state();now[0]=2
        self.assertEqual(a.state(),'idle')
        self.assertEqual(a.music_spent,{})

    def test_bad_policy_is_rejected(self):
        for field,value in [('share',float('nan')),('share',0),('cycles',[1,1.5]),('cooldown_seconds',-1)]:
            policy=copy.deepcopy(POLICY);policy['actions']['sing_guitar'][field]=value
            with self.assertRaises(ValueError): validate_music_policy(policy)

    def test_weak_music_spends_eighty_percent_listening(self):
        a,now=schedule()
        a.music_intensity.profile='weak'
        actual=simulate(a,now,10800)
        self.assertLess(abs(actual['listen']-80),1)
        self.assertLess(actual['roll']+actual['stretch'],3)

    def test_main_actions_last_at_least_forty_five_seconds(self):
        a,now=schedule();a.playing=True;a.state();now[0]=1.01
        for _ in range(100):
            state=a.state()
            if state in ('sing_guitar','spin'):
                self.assertGreaterEqual(a._deadline-now[0],45)
            now[0]=a._deadline

    def test_fidgets_share_cooldown_and_remain_rare(self):
        a,now=schedule();a.playing=True;a.state();now[0]=1.01
        last_end=-10000;count=0
        while now[0]<3600:
            state=a.state()
            if state in ('roll','stretch'):
                self.assertGreaterEqual(now[0]+1e-8,last_end+120)
                last_end=a._deadline;count+=1
            now[0]=a._deadline
        self.assertLessEqual(count,30)

    def test_profile_change_waits_for_loop_boundary(self):
        a,now=schedule();a.playing=True;a.state();now[0]=1.01
        a.state();self.assertEqual(a._auto,'sing_guitar')
        now[0]+=.1;a.music_intensity.profile='weak'
        self.assertEqual(a.state(),'sing_guitar')
        boundary=a._music_profile_pending[1]
        self.assertLessEqual(boundary-now[0],2.436)
        now[0]=boundary;a.state()
        self.assertEqual(a._music_profile,'weak')
        self.assertLess(sum(a.music_spent.values()),.001)
        self.assertGreater(sum(a._music_histories['normal'].values()),2)

    def test_intensity_requires_sustained_change_and_hysteresis(self):
        meter=MusicIntensity()
        for i in range(50): meter.update(i/10,.05)
        self.assertEqual(meter.profile,'normal')
        for i in range(50,100): meter.update(i/10,.05)
        self.assertEqual(meter.profile,'weak')
        for i in range(100,120): meter.update(i/10,1.,True)
        self.assertEqual(meter.profile,'weak')
        for i in range(120,220): meter.update(i/10,1.,True)
        self.assertEqual(meter.profile,'normal')

    def test_missing_audio_is_not_classified_as_weak(self):
        meter=MusicIntensity()
        for i in range(100): meter.update(i/10,None)
        self.assertEqual(meter.profile,'normal')
        for i in range(100,200): meter.update(i/10,.03)
        self.assertEqual(meter.profile,'weak')
        meter.update(30,None)
        self.assertEqual(meter.profile,'normal')

    def test_onset_density_matters_at_the_same_sound_level(self):
        sparse,dense=MusicIntensity(),MusicIntensity()
        for i in range(300):
            sparse.update(i/10,.25)
            dense.update(i/10,.25,i%5==0)
        self.assertEqual(sparse.profile,'weak')
        self.assertEqual(dense.profile,'normal')


if __name__=='__main__': unittest.main()
