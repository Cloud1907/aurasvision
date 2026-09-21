import { createRoot } from 'react-dom/client';
import Panel from './Panel';
import './fonts.css';

import './theme.css';
import './panel.css';

window.AurasUI = {
  mountPanel(element, bridge) {
    const root = createRoot(element);
    root.render(<Panel bridge={bridge}/>);
    return () => root.unmount();
  }
};

import './command-center.css';
