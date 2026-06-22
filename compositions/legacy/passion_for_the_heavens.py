#!python3
from mido import Message, MidiFile, MidiTrack
import random
import datetime as dt


def makeScale(root, low, high, mode):
    scale = []
    for i in range(root, root + 96, 12):
        for j in range(len(mode)):
            note = i + mode[j]
            if note >= low and note <= high:
                scale.append(note)
    return scale
    # return [0,2,4,5,7,9,11]


def makePattern(localtrack, root, pattern):
    # pattern = [7, 7, 4, 7, 7, 4, 7, 9, 9, 12]
    notes = []
    for i in range(len(pattern)):
        localtrack.append(Message('note_on', note=root + pattern[i], velocity=random.randint(70, 90), time=50))
        localtrack.append(Message('note_on', note=root + pattern[i] - 3, velocity=random.randint(70, 90), time=50))


def makeFixedRandomTrack(name, scale, note_length, minutes):
    duration = minutes * 60 * 1000
    print('duration is ', duration)
    track = MidiTrack()
    track.name = name
    track.append(Message('program_change', program=1, time=0))
    total_time = 0
    while total_time < duration - note_length:
        total_time += 100 + note_lengthel1mac
        note = scale[random.randint(0, len(scale) - 1)]
        track.append(Message('note_on', note=note, velocity=84, time=100))
        track.append(Message('note_off', note=note, velocity=84, time=note_length))
        print(total_time)
    return track


def makeRandomWalkTrack(name, scale, short_note, long_note, minutes):
    duration = minutes * 60 * 1000
    track = MidiTrack()
    track.name = name
    total_time = 0
    note = scale[random.randint(0, len(scale) - 1)]
    while total_time < duration - long_note:
        randomStep = random.randint(-2, 2)
        place = scale.index(note)
        note = scale[(place + randomStep) % len(scale)]
        current_rest_length = random.choice(range(1, 960, 120))
        current_note_length = random.choice(range(short_note, long_note, 480))
        track.append(Message('note_on', note=note, velocity=random.randint(61, 96), time=current_rest_length))
        track.append(Message('note_off', note=note, velocity=random.randint(61, 96), time=current_note_length))
        total_time += current_rest_length + current_note_length
    if total_time < duration:
        track.append(Message('note_on', note=note, velocity=random.randint(61, 96), time=0))
        track.append(Message('note_off', note=note, velocity=0, time=duration - total_time))
        print(total_time + duration - total_time)
    return track


def makeDroneTrack(name, droneNotes):
    track = MidiTrack()
    track.name = name
    for note in droneNotes:
        track.append(Message('note_on', note=note, velocity=84, time=0))
        track.append(Message('note_off', note=note, velocity=85, time=60 * 1000))
    return track


def makeRandomTrack(name, scale, short_note, long_note, minutes):
    duration = minutes * 60 * 1000
    track = MidiTrack()
    track.name = name
    total_time = 0
    while total_time < duration - long_note:
        note = scale[random.randint(0, len(scale) - 1)]
        current_rest_length = random.choice(range(1, 960, 120))
        current_note_length = random.choice(range(short_note, long_note, 480))
        track.append(Message('note_on', note=note, velocity=random.randint(61, 96), time=current_rest_length))
        track.append(Message('note_off', note=note, velocity=random.randint(61, 96), time=current_note_length))
        total_time += current_rest_length + current_note_length
    if total_time < duration:
        track.append(Message('note_on', note=note, velocity=random.randint(61, 84), time=0))
        track.append(Message('note_off', note=note, velocity=0, time=duration - total_time))
        print(total_time + duration - total_time)
    return track


def makeRandomChords(scale, short_note, long_note, minutes):
    duration = minutes * 60 * 1000
    track = MidiTrack()
    total_time = 0
    while total_time < duration - long_note:
        note = random.choice(scale)
        current_rest_length = random.choice(range(1, 480, 120))
        current_note_length = random.choice(range(short_note, long_note, 480))
        track.append(Message('note_on', note=note, velocity=100, time=current_rest_length))
        track.append(Message('note_on', note=note + 4, velocity=100, time=0))
        track.append(Message('note_on', note=note + 7, velocity=100, time=0))
        track.append(Message('note_off', note=note, velocity=100, time=current_note_length))
        track.append(Message('note_off', note=note + 4, velocity=100, time=0))
        track.append(Message('note_off', note=note + 7, velocity=100, time=0))
        total_time += current_rest_length + current_note_length
    if total_time < duration:
        track.append(Message('note_on', note=note, velocity=random.randint(61, 84), time=0))
        track.append(Message('note_off', note=note, velocity=0, time=duration - total_time))
        print(total_time + duration - total_time)
    return track


def makeScaleTrack(name, scale, duration):
    track = MidiTrack()
    track.name = name
    for note in scale:
        track.append(Message('note_on', note=note, velocity=84, time=200))
        track.append(Message('note_off', note=note, velocity=84, time=duration))
    return track


def mergeTracks(name, trackA, trackB):
    track = MidiTrack()
    track.name = name
    for message in trackA:
        if message.type == 'note_on' or message.type == 'note_off':
            track.append(message)
    for message in trackB:
        if message.type == 'note_on' or message.type == 'note_off':
            track.append(message)
    return track


def makeMidi(name, tracks):
    now = dt.datetime.now()
    mid = MidiFile()
    for i in range(len(tracks)):
        mid.tracks.append(tracks[i])
    name = name + '_' + str(now.year) + '_' + str(now.month) + '_' + str(now.day) + '_' + str(now.hour) + '_' + str(now.minute) + '_' + str(now.second) + '.mid'
    print(name)
    mid.save(name)


class Mode:
    def major(self):
        return [0, 2, 4, 5, 7, 9, 11]

    def minor(self):
        return [0, 2, 3, 5, 7, 9, 11]

    def pentatonic(self):
        return [0, 2, 3, 7, 9]

    def majorLocrian():
        return [0, 2, 5, 6, 8, 10]

    def dorian(self):
        return [0, 2, 3, 5, 7, 9, 10]

    def phrygian(self):
        return [0, 1, 3, 5, 7, 8, 10]

    def lydian(self):
        return [0, 2, 4, 6, 7, 9, 11]

    def mixolydian(self):
        return [0, 2, 4, 5, 7, 9, 10]

    def aolian(self):
        return [0, 2, 3, 5, 7, 8, 10]

    def arabicDoubleHarmonic(self):
        return [0, 1, 4, 5, 7, 8, 11]


myMode = Mode()

keys = [
    {'key': 28, 'mode': myMode.minor(), 'name': '01e minor'},          # 1
    {'key': 31, 'mode': myMode.major(), 'name': '02g major'},          # 2
    {'key': 35, 'mode': myMode.minor(), 'name': '03b minor'},          # 2,3
    {'key': 26, 'mode': myMode.major(), 'name': '04d major'},          # 4a
    {'key': 24, 'mode': myMode.major(), 'name': '05c major'},          # 4a,4b,4c
    {'key': 33, 'mode': myMode.minor(), 'name': '06a minor'},          # 4c
    {'key': 26, 'mode': myMode.minor(), 'name': '07d minor'},          # 4d
    {'key': 34, 'mode': myMode.minor(), 'name': '08bflat minor'},      # 4e
    {'key': 28, 'mode': myMode.minor(), 'name': '09e minor'},          # 4e
    {'key': 35, 'mode': myMode.minor(), 'name': '10b minor'},          # 5
    {'key': 30, 'mode': myMode.minor(), 'name': '11fsharp minor'},     # 5,6
    {'key': 26, 'mode': myMode.major(), 'name': '12d major'},          # 7
    {'key': 35, 'mode': myMode.minor(), 'name': '13b minor'},          # 7,8
    {'key': 31, 'mode': myMode.major(), 'name': '14g major'},          # 9a,9b,9c
    {'key': 24, 'mode': myMode.major(), 'name': '15c major'},          # 9c
    {'key': 29, 'mode': myMode.minor(), 'name': '16f minor'},          # 9e
    {'key': 24, 'mode': myMode.minor(), 'name': '17c minor'},          # 9e
    {'key': 32, 'mode': myMode.major(), 'name': '18aflat major'},      # 10
    {'key': 29, 'mode': myMode.minor(), 'name': '19f minor'},          # 11
    {'key': 31, 'mode': myMode.major(), 'name': '20g major'},          # 11
    {'key': 28, 'mode': myMode.minor(), 'name': '21e minor'},          # 12
    {'key': 24, 'mode': myMode.major(), 'name': '21c major'},          # 12
    {'key': 31, 'mode': myMode.major(), 'name': '22g major'},          # 13
    {'key': 35, 'mode': myMode.minor(), 'name': '23b minor'},          # 14
    {'key': 28, 'mode': myMode.major(), 'name': '24e major'},          # 15
    {'key': 33, 'mode': myMode.major(), 'name': '25a major'},          # 16
    {'key': 31, 'mode': myMode.minor(), 'name': '26g minor'},          # 16
    {'key': 26, 'mode': myMode.major(), 'name': '27eflat major'},      # 17
    {'key': 29, 'mode': myMode.major(), 'name': '28f major'},          # 18
    {'key': 32, 'mode': myMode.major(), 'name': '29aflat major'},      # 18
    {'key': 29, 'mode': myMode.minor(), 'name': '30f minor'},          # 19
    {'key': 31, 'mode': myMode.major(), 'name': '31g major'},          # 19
    {'key': 24, 'mode': myMode.minor(), 'name': '32c minor'},          # 20
    {'key': 35, 'mode': myMode.major(), 'name': '33b major'},          # 21
    {'key': 31, 'mode': myMode.major(), 'name': '34g major'},          # 21
    {'key': 26, 'mode': myMode.minor(), 'name': '35d minor'},          # 22
    {'key': 34, 'mode': myMode.major(), 'name': '36bflat major'},      # 22
    {'key': 31, 'mode': myMode.minor(), 'name': '37g minor'},          # 23
    {'key': 29, 'mode': myMode.major(), 'name': '38f major'},          # 24
    {'key': 35, 'mode': myMode.minor(), 'name': '39b minor'},          # 24, 25
    {'key': 26, 'mode': myMode.major(), 'name': '40d major'},          # 26
    {'key': 31, 'mode': myMode.major(), 'name': '41g major'},          # 26
    {'key': 28, 'mode': myMode.minor(), 'name': '42e minor'},          # 27a,27b
    {'key': 30, 'mode': myMode.major(), 'name': '43fsharp major'},     # 28
    {'key': 25, 'mode': myMode.minor(), 'name': '44csharp minor'},     # 28
    {'key': 28, 'mode': myMode.minor(), 'name': '45e minor'},          # 29
]

segments = []
for item in keys:
    soprano_scale = makeScale(item['key'], 72, 84, item['mode'])
    segments.append(makeRandomWalkTrack(item['name'] + ' soprano', soprano_scale, 1000, 3000, 1))

sopranoTrack = MidiTrack()
for track in segments:
    for message in track:
        if message.type == 'note_on' or message.type == 'note_off':
            sopranoTrack.append(message)

print('tenors')
segments = []
for item in keys:
    tenor_scale = makeScale(item['key'], 48, 72, item['mode'])
    segments.append(makeRandomTrack(item['name'] + ' tenor_random', tenor_scale, 3000, 4000, 1))

tenorRandomTrack = MidiTrack()
for track in segments:
    for message in track:
        if message.type == 'note_on' or message.type == 'note_off':
            tenorRandomTrack.append(message)

print('tenors')
segments = []
for item in keys:
    tenor_scale = makeScale(item['key'], 48, 72, item['mode'])
    segments.append(makeRandomWalkTrack(item['name'] + ' tenor_walk', tenor_scale, 3000, 4000, 1))

tenorWalkTrack = MidiTrack()
for track in segments:
    for message in track:
        if message.type == 'note_on' or message.type == 'note_off':
            tenorWalkTrack.append(message)

print('bass')
segments = []
for item in keys:
    bass_scale = makeScale(item['key'], 24, 48, item['mode'])
    segments.append(makeRandomWalkTrack(item['name'] + ' bass', bass_scale, 1000, 2000, 1))

bassTrack = MidiTrack()
for track in segments:
    for message in track:
        if message.type == 'note_on' or message.type == 'note_off':
            bassTrack.append(message)

droneNotes = [28, 31, 35, 26, 24, 33, 26, 34, 28, 35, 30, 26, 35, 31, 24, 29, 24, 32, 29, 31, 28, 24, 31, 35, 28, 33, 31, 26, 29, 32, 29, 31, 24, 35, 31, 26, 34, 31, 29, 35, 26, 31, 28, 30, 25, 28]
droneTrack = makeDroneTrack('drone', droneNotes)

makeMidi('Passion_for_the_heavens', [sopranoTrack, tenorWalkTrack, tenorRandomTrack, bassTrack, droneTrack])
# makeMidi('Passion_for_the_heavens_drone', [droneTrack])
print('thats all folks')
