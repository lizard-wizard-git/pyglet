"""High-level sound and video player."""
from __future__ import print_function
from __future__ import division
from builtins import object
# ----------------------------------------------------------------------------
# pyglet
# Copyright (c) 2006-2008 Alex Holkner
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions
# are met:
#
#  * Redistributions of source code must retain the above copyright
#    notice, this list of conditions and the following disclaimer.
#  * Redistributions in binary form must reproduce the above copyright
#    notice, this list of conditions and the following disclaimer in
#    the documentation and/or other materials provided with the
#    distribution.
#  * Neither the name of pyglet nor the names of its
#    contributors may be used to endorse or promote products
#    derived from this software without specific prior written
#    permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
# "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
# LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS
# FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE
# COPYRIGHT OWNER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT,
# INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING,
# BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
# LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
# CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT
# LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN
# ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.
# ----------------------------------------------------------------------------

import pyglet
from pyglet.media import buffered_logger as bl
from pyglet.media.drivers import get_audio_driver
from pyglet.media.sources.base import PlayList

# import cProfile

_debug = pyglet.options['debug_media']

clock = pyglet.clock.get_default()


class MasterClock(object):
    def __init__(self):
        self._time = 0.0
        self._systime = None

    def play(self):
        self._systime = clock.time()

    def pause(self):
        self._time = self.get_time()
        self._systime = None

    def reset(self):
        self._time = 0.0
        if self._systime is not None:
            self._systime = clock.time()

    def get_time(self):
        """
        Current master clock time.
        """
        if self._systime is None:
            now = self._time
        else:
            now = clock.time() - self._systime + self._time
        return now

    def set_time(self, value):
        """
        Set the master clock time.

        :param float value: The new 
            :py:class:`~pyglet.media.player.MasterClock` time.
        """
        self.reset()
        self._time = value


class Player(pyglet.event.EventDispatcher):
    """High-level sound and video player.
    """

    _texture = None

    # Spacialisation attributes, preserved between audio players
    _volume = 1.0
    _min_distance = 1.0
    _max_distance = 100000000.

    _position = (0, 0, 0)
    _pitch = 1.0

    _cone_orientation = (0, 0, 1)
    _cone_inner_angle = 360.
    _cone_outer_angle = 360.
    _cone_outer_gain = 1.

    def __init__(self):
        self._playlist = PlayList()
        self._audio_player = None

        # Desired play state (not an indication of actual state).
        self._playing = False

        self._mclock = MasterClock()
        #: Loop the current source indefinitely or until
        #: :py:meth:`Player.next_source` is called.  Initially False.
        #:
        #: :type: bool
        self.loop = False

        # self.pr = cProfile.Profile()

    def __del__(self):
        self.delete()

    def queue(self, source):
        """
        Queue the source on this player.

        If the player has no source, the player will be paused immediately
        on this source.

        :param pyglet.media.Source source: The source to queue.
        """
        self._playlist.queue(source)
        self._set_playing(self._playing)

    def _set_playing(self, playing):
        #stopping = self._playing and not playing
        #starting = not self._playing and playing

        self._playing = playing
        source = self.source

        if playing and source:
            if source.audio_format:
                if self._audio_player is None:
                    self._create_audio_player()
                if self._audio_player:
                    # We succesfully created an audio player
                    self._audio_player.prefill_audio()

            if bl.logger is not None:
                bl.logger.init_wall_time()
                bl.logger.log("p.P._sp", 0.0)
            
            if source.video_format:
                if not self._texture:
                    self._create_texture()
            
            if self._audio_player:
                self._audio_player.play()
            if source.video_format:
                pyglet.clock.schedule_once(self.update_texture, 0)
            # For audio synchronization tests, the following will
            # add a delay to de-synchronize the audio.
            # Negative number means audio runs ahead.
            # self._mclock._systime += -0.3
            self._mclock.play()
        else:
            if self._audio_player:
                self._audio_player.stop()

            pyglet.clock.unschedule(self.update_texture)
            self._mclock.pause()
            
    def _get_playing(self):
        """
        Read-only. Determine if the player state is playing.

        The *playing* property is irrespective of whether or not there is
        actually a source to play. If *playing* is ``True`` and a source is
        queued, it will begin playing immediately. If *playing* is ``False``,
        it is implied that the player is paused. There is no other possible
        state.
        """
        return self._playing

    playing = property(_get_playing)

    def play(self):
        """
        Begin playing the current source.

        This has no effect if the player is already playing.
        """
        self._set_playing(True)

    def pause(self):
        """
        Pause playback of the current source.

        This has no effect if the player is already paused.
        """
        self._set_playing(False)

    def delete(self):
        """Tear down the player and any child objects."""
        if self._audio_player:
            self._audio_player.delete()
            self._audio_player = None

    def next_source(self):
        """
        Move immediately to the next queued source.

        There may be a gap in playback while the audio buffer is refilled.
        """

        was_playing = self._playing
        self.pause()
        self._mclock.reset()

        playlist = self._playlist
        if playlist.has_next():
            old_audio_format = playlist.audio_format
            old_video_format = playlist.video_format
            playlist.next_source()
            if old_audio_format == playlist.audio_format:
                self._audio_player.clear()
            else:
                self._audio_player.delete()
                self._audio_player = None
            if old_video_format != playlist.video_format:
                self._texture = None
                pyglet.clock.unschedule(self.update_texture)

            self._set_playing(was_playing)
            self.dispatch_event('on_player_next_source')
        else:
            self.delete()
            playlist.next_source()
            self.dispatch_event('on_player_eos')
            self.dispatch_event('on_playlist_exhausted') # Not really needed anymore...


    #: :deprecated: Use `next_source` instead.
    next = next_source  # old API, worked badly with 2to3

    def seek(self, time):
        """
        Seek for playback to the indicated timestamp in seconds on the current
        source. If the timestamp is outside the duration of the source, it
        will be clamped to the end.
        """
        playing = self._playing
        if playing:
            self.pause()
        if not self.source:
            return

        if bl.logger is not None:
            bl.logger.log("p.P.sk", time)

        self._mclock.set_time(time)
        self.source.seek(time)
        if self._audio_player:
            # XXX: According to docstring in AbstractAudioPlayer this cannot be called when the
            # player is not stopped
            self._audio_player.clear()
        if self.source.video_format:
            self.update_texture()
            pyglet.clock.unschedule(self.update_texture)
        self._set_playing(playing)

    def _create_audio_player(self):
        assert not self._audio_player
        assert self.source

        _playlist = self._playlist
        audio_driver = get_audio_driver()
        if audio_driver is None:
            # Failed to find a valid audio driver
            self.source.audio_format = None
            return
        
        self._audio_player = audio_driver.create_audio_player(_playlist, self)

        _class = self.__class__
        def _set(name):
            private_name = '_' + name
            value = getattr(self, private_name) 
            if value != getattr(_class, private_name):
                getattr(self._audio_player, 'set_' + name)(value)
        _set('volume')
        _set('min_distance')
        _set('max_distance')
        _set('position')
        _set('pitch')
        _set('cone_orientation')
        _set('cone_inner_angle')
        _set('cone_outer_angle')
        _set('cone_outer_gain')

    def _get_source(self):
        """Read-only. The current :py:class:`Source`, or ``None``."""
        return self._playlist.get_current_source()

    source = property(_get_source)

    def _get_time(self):
        """
        Read-only. Current playback time of the current source.

        The playback time is a float expressed in seconds, with 0.0 being the
        beginning of the media. The playback time returned represents the 
        player master clock time.
        """
        return self._mclock.get_time()

    time = property(_get_time)

    def _create_texture(self):
        video_format = self.source.video_format
        self._texture = pyglet.image.Texture.create(
            video_format.width, video_format.height, rectangle=True)
        self._texture = self._texture.get_transform(flip_y=True)
        # After flipping the texture along the y axis, the anchor_y is set
        # to the top of the image. We want to keep it at the bottom.
        self._texture.anchor_y = 0
        return self._texture

    def get_texture(self):
        """
        Get the texture for the current video frame.

        You should call this method every time you display a frame of video,
        as multiple textures might be used. The return value will be None if
        there is no video in the current source.

        :return: :py:class:`pyglet.image.Texture`
        """
        return self._texture

    def seek_next_frame(self):
        """Step forwards one video frame in the current Source.
        """
        time = self._playlist.get_next_video_timestamp()
        if time is None:
            return
        self.seek(time)

    def update_texture(self, dt=None):
        """Manually update the texture from the current source. This happens
        automatically, so you shouldn't need to call this method.
        """
        # self.pr.disable()
        # if dt > 0.05:
        #     print("update_texture dt:", dt)
        #     import pstats
        #     ps = pstats.Stats(self.pr).sort_stats("cumulative")
        #     ps.print_stats()
        if bl.logger is not None:
            bl.logger.log("p.P.ut.1.0", dt, time, bl.logger.rebased_wall_time())
        _playlist = self._playlist
        time = self.time
        if bl.logger is not None:
            bl.logger.log(
                "p.P.ut.1.2",
                time,
                self._audio_player.get_time() if self._audio_player else 0
            )

        frame_rate = _playlist.video_format.frame_rate
        frame_duration = 1 / frame_rate
        ts = _playlist.get_next_video_timestamp()
        while ts is not None and ts + frame_duration < time: # Allow up to frame_duration difference
            _playlist.get_next_video_frame() # Discard frame
            if bl.logger is not None:
                bl.logger.log("p.P.ut.1.5", ts)
            ts = _playlist.get_next_video_timestamp()

        if bl.logger is not None:
            bl.logger.log("p.P.ut.1.6", ts)

        if ts is None:
            # No more video frames to show. End of video stream.
            if bl.logger is not None:
                bl.logger.log("p.P.ut.1.7", frame_duration)
            
            pyglet.clock.schedule_once(self._video_finished, 0)
            return

        image = _playlist.get_next_video_frame()
        if image is not None:
            if self._texture is None:
                self._create_texture()
            self._texture.blit_into(image, 0, 0, 0)
        elif bl.logger is not None:
            bl.logger.log("p.P.ut.1.8")
        
        ts = _playlist.get_next_video_timestamp()
        if ts is None:
            delay = frame_duration
        else:
            delay = ts - time

        if bl.logger is not None:
            bl.logger.log("p.P.ut.1.9", delay, ts)
        pyglet.clock.schedule_once(self.update_texture, delay)
        # self.pr.enable()

    def _video_finished(self, dt):
        if self._audio_player is None:
            self.dispatch_event("on_eos")

    def _player_property(name, doc=None):
        private_name = '_' + name
        set_name = 'set_' + name
        def _player_property_set(self, value):
            setattr(self, private_name, value)
            if self._audio_player:
                getattr(self._audio_player, set_name)(value)

        def _player_property_get(self):
            return getattr(self, private_name)

        return property(_player_property_get, _player_property_set, doc=doc)

    volume = _player_property('volume', doc="""
    The volume level of sound playback.

    The nominal level is 1.0, and 0.0 is silence.

    The volume level is affected by the distance from the listener (if
    positioned).
    """)
    min_distance = _player_property('min_distance', doc="""
    The distance beyond which the sound volume drops by half, and within
    which no attenuation is applied.

    The minimum distance controls how quickly a sound is attenuated as it
    moves away from the listener. The gain is clamped at the nominal value
    within the min distance. By default the value is 1.0.

    The unit defaults to meters, but can be modified with the listener properties.
    """)
    max_distance = _player_property('max_distance', doc="""
    The distance at which no further attenuation is applied.

    When the distance from the listener to the player is greater than this
    value, attenuation is calculated as if the distance were value. By
    default the maximum distance is infinity.

    The unit defaults to meters, but can be modified with the listener
    properties.
    """)
    position = _player_property('position', doc="""
    The position of the sound in 3D space.

    The position is given as a tuple of floats (x, y, z). The unit
    defaults to meters, but can be modified with the listener properties.
    """)
    pitch = _player_property('pitch', doc="""
    The pitch shift to apply to the sound.

    The nominal pitch is 1.0. A pitch of 2.0 will sound one octave higher,
    and play twice as fast. A pitch of 0.5 will sound one octave lower, and
    play twice as slow. A pitch of 0.0 is not permitted.
    """)
    cone_orientation = _player_property('cone_orientation', doc="""
    The direction of the sound in 3D space.

    The direction is specified as a tuple of floats (x, y, z), and has no
    unit. The default direction is (0, 0, -1). Directional effects are only
    noticeable if the other cone properties are changed from their default
    values.
    """)
    cone_inner_angle = _player_property('cone_inner_angle', doc="""
    The interior angle of the inner cone.

    The angle is given in degrees, and defaults to 360. When the listener
    is positioned within the volume defined by the inner cone, the sound is
    played at normal gain (see :py:attr:`volume`).
    """)
    cone_outer_angle = _player_property('cone_outer_angle', doc="""
    The interior angle of the outer cone.

    The angle is given in degrees, and defaults to 360. When the listener
    is positioned within the volume defined by the outer cone, but outside
    the volume defined by the inner cone, the gain applied is a smooth
    interpolation between :py:attr:`volume` and :py:attr:`cone_outer_gain`.
    """)
    cone_outer_gain = _player_property('cone_outer_gain', doc="""
    The gain applied outside the cone.

    When the listener is positioned outside the volume defined by the outer
    cone, this gain is applied instead of :py:attr:`volume`.
    """)

    # Events

    def on_player_eos(self):
        """The player ran out of sources. The playlist is empty.

        :event:
        """
        if _debug:
            print('Player.on_player_eos')

    def on_playlist_exhausted(self):
        """The current playlist ran out of data.

        :event:
        """
        if _debug:
            print('Player.on_playlist_exhausted')

    def on_eos(self):
        """The current source ran out of data.

        The default behaviour is to advance to the next source  in the 
        playlist.

        :event:
        """
        if _debug:
            print('Player.on_eos')
        if bl.logger is not None:
            bl.logger.log("p.P.oe")
            bl.logger.close()
        if self.loop:
            self.seek(0)
        else:
            self.next_source()

    def on_player_next_source(self):
        """The player starts to play the next source in the playlist

        :event:
        """
        pass

Player.register_event_type('on_eos')
Player.register_event_type('on_player_eos')
Player.register_event_type('on_playlist_exhausted')
Player.register_event_type('on_player_next_source')


class PlayerGroup(object):
    """Group of players that can be played and paused simultaneously.

    :Ivariables:
        `players` : list of `Player`
            Players in this group.

    """

    def __init__(self, players):
        """Create a player group for the given set of players.

        All players in the group must currently not belong to any other
        group.

        :Parameters:
            `players` : Sequence of `Player`
                Players to add to this group.

        """
        self.players = list(players)

    def play(self):
        """Begin playing all players in the group simultaneously.
        """
        audio_players = [p._audio_player \
                         for p in self.players if p._audio_player]
        if audio_players:
            audio_players[0]._play_group(audio_players)
        for player in self.players:
            player.play()

    def pause(self):
        """Pause all players in the group simultaneously.
        """
        audio_players = [p._audio_player \
                         for p in self.players if p._audio_player]
        if audio_players:
            audio_players[0]._stop_group(audio_players)
        for player in self.players:
            player.pause()


