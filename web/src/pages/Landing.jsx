import {
  IconArrow, IconBroadcast, IconCheck, IconDownload, IconSearch, IconShells,
  IconSplit, IconWindows, IconWorkspace,
} from "../icons.jsx";

// Set once, used everywhere a link needs it.
export const GITHUB = "https://github.com/idk-arsh/multiterm";
export const RELEASES = GITHUB + "/releases/latest";

const FEATURES = [
  [IconWorkspace, "A project remembers its own layout",
   "Save a folder as a workspace and every folder inside becomes a pane. Reopen it and the same terminals come back, in the same shape, in the same directories."],
  [IconArrow, "Each pane starts its own command",
   "Give api, web, worker and tests the command each one should run. Opening the workspace starts all four. No startup script, no JSON to hand edit."],
  [IconBroadcast, "Type once, run it everywhere",
   "Broadcast sends every keystroke to every pane in the tab. Pull four repos or restart three services in one go."],
  [IconSplit, "Panes in any shape, kept that way",
   "Drag a divider and the layout is yours. It is a split tree, not a fixed grid, and the shape is saved with the workspace."],
  [IconSearch, "Find across the scrollback",
   "Ctrl+F highlights every match in the pane and steps through them. An overlay scrollbar and a jump back to the newest output come with it."],
  [IconShells, "Every shell you already have",
   "Command Prompt, PowerShell, PowerShell 7, Git Bash, WSL and Python, each pane in its own folder, all in one window."],
];

const STEPS = [
  [IconDownload, "Download the exe", "One file from the releases page. No installer, no admin rights."],
  [IconWorkspace, "Add a workspace", "Point it at a project folder. The folders inside show up in the sidebar."],
  [IconArrow, "Set what each folder runs", "Right-click a folder, type the command. It is saved with the workspace."],
  [IconCheck, "Open it", "Press the arrow on the workspace. Every folder opens as a terminal and starts its command."],
];

const COMPARISON = [
  ["Split panes and tabs", "Yes", "Yes, this part is not the difference"],
  ["Open a saved project layout", "One click per workspace", "Hand written JSON, if at all"],
  ["Start a command per pane", "Saved with the folder", "Not without scripting it yourself"],
  ["Type into every pane at once", "Built in", "Not available"],
  ["Source", "MIT, on GitHub", "Varies"],
];

export default function Landing() {
  return (
    <>
      <header className="wrap hero">
        <div className="hero-copy">
          <p className="eyebrow">
            <span className="eyebrow-price">Free and open source</span>
            <span className="eyebrow-sep" />
            <span>Windows 10 and 11</span>
          </p>
          <h1>
            Open your project,
            <span className="grad"> not six terminals.</span>
          </h1>
          <p className="lede">
            Your terminal can split panes. It cannot remember that this project
            means four folders, that each one runs a different command, and
            start them all in one click. MultiTerm saves that as a workspace
            and lets you type one command into every pane at once.
          </p>
          <div className="hero-cta">
            <a className="btn btn-primary btn-lg" href={RELEASES}>
              <IconDownload width="18" height="18" />
              Download for Windows
            </a>
            <a className="btn btn-ghost btn-lg" href={GITHUB}>
              View the source
            </a>
          </div>
          <ul className="hero-facts">
            <li><IconWindows width="17" height="17" /> Single executable</li>
            <li><IconCheck width="17" height="17" /> MIT licensed</li>
            <li><IconCheck width="17" height="17" /> No account, no telemetry</li>
          </ul>
        </div>

        <figure className="hero-media">
          <div className="media-frame">
            <img src="/demo.webp"
                 alt="MultiTerm opening a workspace, running a command in every pane at once, and resizing panes by dragging a divider"
                 width="1200" height="738" loading="eager" decoding="async" />
          </div>
        </figure>
      </header>

      <section className="wrap">
        <div className="section-head">
          <h2>Built for the project you open every morning</h2>
          <p>
            Six terminals, four directories, the same four commands, every day.
            That is the part worth automating.
          </p>
        </div>
        <div className="grid">
          {FEATURES.map(([Icon, title, body]) => (
            <article className="card" key={title}>
              <span className="card-icon"><Icon /></span>
              <h3>{title}</h3>
              <p>{body}</p>
            </article>
          ))}
        </div>
      </section>

      <section className="wrap">
        <div className="section-head">
          <h2>Running in about two minutes</h2>
          <p>Four steps from this page to a project that starts itself.</p>
        </div>
        <ol className="steps-grid">
          {STEPS.map(([Icon, title, body], i) => (
            <li key={title}>
              <span className="step-no">{i + 1}</span>
              <span className="step-icon"><Icon width="20" height="20" /></span>
              <h3>{title}</h3>
              <p>{body}</p>
            </li>
          ))}
        </ol>
      </section>

      <section className="wrap">
        <div className="section-head">
          <h2>What you cannot do by splitting a terminal</h2>
          <p>
            Windows Terminal already gives you panes, tabs and themes. Nothing
            here replaces that. The difference is that MultiTerm treats a
            project as a saved thing that starts itself.
          </p>
        </div>
        <div className="compare">
          <div className="compare-row compare-head">
            <span />
            <span className="compare-us">MultiTerm</span>
            <span>A split terminal</span>
          </div>
          {COMPARISON.map(([label, ours, theirs]) => (
            <div className="compare-row" key={label}>
              <span className="compare-label">{label}</span>
              <span className="compare-us">
                <IconCheck width="17" height="17" /> {ours}
              </span>
              <span className="compare-them">{theirs}</span>
            </div>
          ))}
        </div>
      </section>

      <section className="wrap">
        <div className="section-head">
          <h2>How it is built</h2>
          <p>
            No Electron, no web view. Python and Tk, with the terminal emulator
            and the whole interface drawn on canvases. A VT100/xterm parser
            written for it, one ConPTY child per pane, a split tree for layout,
            and a renderer that repaints only the rows that changed. Four panes
            streaming thousands of lines each still run at about 70 frames a
            second. The tests drive the real window.
          </p>
        </div>
      </section>

      <section className="wrap">
        <div className="cta-panel">
          <div>
            <h2>Try it on the project you open most</h2>
            <p>
              If your day is one or two shells, the built in terminal is fine and
              you should keep using it. If it is four terminals in four folders
              every morning, this saves you the setup.
            </p>
          </div>
          <a className="btn btn-primary btn-lg" href={RELEASES}>
            <IconDownload width="18" height="18" />
            Download for Windows
          </a>
        </div>
      </section>
    </>
  );
}
