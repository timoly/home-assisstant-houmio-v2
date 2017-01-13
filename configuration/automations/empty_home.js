alias: 'Empty house'
trigger:
  - platform: state
    entity_id: group.all_devices
    from: 'home'
    to: 'not_home'
    for:
      hours: 0
      minutes: 5
      seconds: 0
action:
  service: group.turn_off
  entity_id: group.all_lights
