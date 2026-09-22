const { test } = require('node:test');
const assert = require('node:assert/strict');
const { pathToFileURL } = require('node:url');
const path = require('node:path');
const modulePath = pathToFileURL(path.resolve(__dirname, '../frontend/notification-policy.mjs'));

test('camera, type and cooldown decide whether a new alarm notifies', async () => {
  const { NotificationPolicy } = await import(modulePath);
  const policy = new NotificationPolicy();
  const rules = [{ id: 'rule', camera_id: 'cam', kind: 'sigara', enabled: true, popup: true, sound: true, cooldown: 60 }];
  assert.equal(policy.accept({ id: 1, camera_id: 'other', kind: 'sigara' }, rules, 1000), null);
  assert.equal(policy.accept({ id: 2, camera_id: 'cam', kind: 'telefon' }, rules, 1000), null);
  assert.equal(policy.accept({ id: 3, camera_id: 'cam', kind: 'sigara' }, rules, 1000).sound, true);
  assert.equal(policy.accept({ id: 3, camera_id: 'cam', kind: 'sigara' }, rules, 70000), null);
  assert.equal(policy.accept({ id: 4, camera_id: 'cam', kind: 'sigara' }, rules, 2000), null);
  assert.ok(policy.accept({ id: 5, camera_id: 'cam', kind: 'sigara' }, rules, 62000));
});

test('acknowledged alarms and disabled rules never notify', async () => {
  const { NotificationPolicy } = await import(modulePath);
  const policy = new NotificationPolicy();
  const rule = { id: 'x', camera_id: 'cam', kind: 'fire', enabled: true, cooldown: 0 };
  assert.equal(policy.accept({ id: 1, camera_id: 'cam', kind: 'fire_warning', acked_at: 'now' }, [rule], 0), null);
  assert.equal(policy.accept({ id: 2, camera_id: 'cam', kind: 'fire_warning' }, [{ ...rule, enabled: false }], 0), null);
  assert.ok(policy.accept({ id: 3, camera_id: 'cam', kind: 'fire_warning' }, [rule], 0));
});
