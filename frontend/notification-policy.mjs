// Olay tekilleştirme görsel bileşen ömründen bağımsızdır.
export class NotificationPolicy {
  constructor() { this.seen = new Set(); this.last = new Map(); }

  accept(alert, rules, now = Date.now()) {
    if (this.seen.has(alert.id)) return null;
    this.seen.add(alert.id);
    if (this.seen.size > 5000) this.seen.delete(this.seen.values().next().value);
    if (alert.acked_at) return null;
    const kind = alert.kind === 'fire_warning' ? 'fire' : alert.kind;
    const matches = rules.filter(rule => rule.enabled && rule.camera_id === alert.camera_id &&
      rule.kind === kind && (!this.last.has(rule.id) ||
        now - this.last.get(rule.id) >= rule.cooldown * 1000));
    if (!matches.length) return null;
    matches.forEach(rule => this.last.set(rule.id, now));
    return { ...alert,
      popup: matches.some(rule => rule.popup),
      sound: matches.some(rule => rule.sound),
      tone: matches.some(rule => rule.sound && rule.tone === 'urgent') ? 'urgent' : 'soft' };
  }
}
