import { createRoot } from 'react-dom/client';
import Panel from './Panel';
import WelcomeGate from './WelcomeGate';
import { NotificationPolicy } from './notification-policy.mjs';
import './fonts.css';

import './theme.css';
import './panel.css';

window.AurasUI = {
  createNotificationPolicy() { return new NotificationPolicy(); },
  mountPanel(element, bridge) {
    const root = createRoot(element);
    root.render(<Panel bridge={bridge}/>);
    return () => root.unmount();
  },
  mountWelcome(element, options) {
    const root = createRoot(element);
    root.render(<WelcomeGate {...options}/>);
    return () => root.unmount();
  }
};

import './command-center.css';
