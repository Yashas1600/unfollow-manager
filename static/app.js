const state = {
  step: 1, // 1=login, 2=scan, 3=review, 4=unfollow
  nonFollowers: [],
  selected: new Set(),
  unfollowStatuses: {},
  originalFollowing: 0,
  originalNonFollowers: 0,
};

// ── Elements ──────────────────────────────────────────────────────────

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => document.querySelectorAll(sel);

// ── Step Management ───────────────────────────────────────────────────

function setStep(n) {
  state.step = n;
  $$(".step").forEach((el, i) => {
    el.classList.remove("active", "done");
    if (i + 1 === n) el.classList.add("active");
    else if (i + 1 < n) el.classList.add("done");
  });
  $(".card-login").classList.toggle("hidden", n !== 1);
  $(".card-scan").classList.toggle("hidden", n !== 2);
  $(".card-review").classList.toggle("hidden", n < 3);
}

// ── Step 1: Login ─────────────────────────────────────────────────────

async function openBrowser() {
  const btn = $("#btn-open-browser");
  btn.disabled = true;
  btn.textContent = "Opening...";

  const res = await fetch("/start-login", { method: "POST" });
  const data = await res.json();

  if (data.status === "ok" || data.status === "already_open") {
    $(".login-status").textContent = "Browser opened — log into Instagram, then click below.";
    $("#btn-confirm-login").classList.remove("hidden");
    btn.textContent = "Browser Opened";
  } else {
    $(".login-status").textContent = "Failed to open browser. Make sure Chromium is installed: python3 -m playwright install chromium";
    btn.disabled = false;
    btn.textContent = "Retry";
  }
}

function confirmLogin() {
  setStep(2);
  startScan();
}

// ── Step 2: Scan ──────────────────────────────────────────────────────

async function startScan() {
  $(".scan-status").classList.remove("hidden");
  $(".scan-status").innerHTML = '<span class="spinner"></span> Detecting your account...';

  await fetch("/scan", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
  });

  pollScan();
}

async function pollScan() {
  const res = await fetch("/scan-status");
  const data = await res.json();

  $(".scan-status").innerHTML =
    '<span class="spinner"></span> ' + (data.message || "Scanning...");

  if (data.status === "done") {
    state.nonFollowers = data.non_followers;
    state.selected = new Set(data.non_followers);

    // Show stats — use profile counts as the main number
    const profFollowers = data.profile_follower_count || data.followers.length;
    const profFollowing = data.profile_following_count || data.following.length;
    state.originalFollowing = profFollowing;
    state.originalNonFollowers = data.non_followers.length;
    $(".stat-followers .stat-number").textContent = profFollowers.toLocaleString();
    $(".stat-following .stat-number").textContent = profFollowing.toLocaleString();
    $(".stat-nonfollowers .stat-number").textContent = data.non_followers.length.toLocaleString();

    // Show note if fetched count differs from profile count
    const followerDiff = profFollowers - data.followers.length;
    const followingDiff = profFollowing - data.following.length;
    if (followerDiff > 0) {
      $(".stat-followers .stat-label").textContent = `FOLLOWERS (${followerDiff} inaccessible)`;
    }
    if (followingDiff > 0) {
      $(".stat-following .stat-label").textContent = `FOLLOWING (${followingDiff} inaccessible)`;
    }

    $(".scan-status").innerHTML = "Scan complete!";
    renderUserList();
    setStep(3);
    return;
  }

  if (data.status === "error") {
    $(".scan-status").innerHTML = "Error: " + data.message;
    $("#btn-scan").disabled = false;
    return;
  }

  setTimeout(pollScan, 1000);
}

// ── Step 3: Review ────────────────────────────────────────────────────

function renderUserList() {
  const list = $(".user-list");
  list.innerHTML = "";

  state.nonFollowers.forEach((username) => {
    const item = document.createElement("div");
    item.className = "user-item";
    item.dataset.username = username;

    const checked = state.selected.has(username) ? "checked" : "";
    const status = state.unfollowStatuses[username];
    let statusHtml = "";
    if (status) {
      const cls =
        status === "success"
          ? "status-success"
          : status === "skip"
          ? "status-skip"
          : status.startsWith("waiting")
          ? "status-waiting"
          : "status-error";
      const label =
        status === "success"
          ? "Unfollowed"
          : status === "skip"
          ? "Skipped"
          : status.startsWith("waiting")
          ? status
          : "Error";
      statusHtml = `<span class="status ${cls}">${label}</span>`;
    }

    item.innerHTML = `
      <input type="checkbox" ${checked} onchange="toggleUser('${username}', this.checked)">
      <span class="username"><a href="https://www.instagram.com/${username}/" target="_blank">@${username}</a></span>
      ${statusHtml}
    `;
    list.appendChild(item);
  });

  updateSelectedCount();
}

function toggleUser(username, checked) {
  if (checked) state.selected.add(username);
  else state.selected.delete(username);
  updateSelectedCount();
}

function selectAll() {
  state.selected = new Set(state.nonFollowers);
  renderUserList();
}

function deselectAll() {
  state.selected.clear();
  renderUserList();
}

function updateSelectedCount() {
  const text = `${state.selected.size} / ${state.nonFollowers.length} selected`;
  $$(".selected-count").forEach(el => el.textContent = text);
  $("#btn-unfollow").disabled = state.selected.size === 0;
}

function updateLiveStats() {
  const successCount = Object.values(state.unfollowStatuses).filter(s => s === "success").length;
  $(".stat-following .stat-number").textContent = (state.originalFollowing - successCount).toLocaleString();
  $(".stat-nonfollowers .stat-number").textContent = (state.originalNonFollowers - successCount).toLocaleString();
}

// ── Step 4: Unfollow ──────────────────────────────────────────────────

async function startUnfollow() {
  if (
    !confirm(
      `Unfollow ${state.selected.size} accounts? This cannot be undone.`
    )
  )
    return;

  const usernames = Array.from(state.selected);
  setStep(4);
  $(".progress-text").textContent = `Unfollowing 0 of ${usernames.length}...`;
  $(".progress-bar").style.width = "0%";
  $(".progress-section").classList.remove("hidden");
  $("#btn-unfollow").disabled = true;

  await fetch("/unfollow", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ usernames }),
  });

  pollUnfollow();
}

async function pollUnfollow() {
  const res = await fetch("/unfollow-status");
  const data = await res.json();

  // Update statuses from server
  if (data.statuses) {
    Object.assign(state.unfollowStatuses, data.statuses);
  }

  const pct =
    data.total > 0 ? Math.round((data.completed / data.total) * 100) : 0;
  $(".progress-bar").style.width = pct + "%";
  $(".progress-text").textContent = `Unfollowed ${data.completed} of ${data.total}`;

  // Update following and non-mutual counts live
  updateLiveStats();
  renderUserList();

  if (data.total > 0 && data.completed >= data.total) {
    showDoneScreen(data.completed, data.total);
    return;
  }

  if (!data.active && data.completed > 0) {
    showDoneScreen(data.completed, data.total);
    return;
  }

  setTimeout(pollUnfollow, 2000);
}

function showDoneScreen(completed, total) {
  const skipped = Object.values(state.unfollowStatuses).filter(s => s === "skip").length;
  const successes = Object.values(state.unfollowStatuses).filter(s => s === "success").length;
  const errors = Object.values(state.unfollowStatuses).filter(s => s !== "success" && s !== "skip").length;

  updateLiveStats();

  // Show done banner above the list
  $(".progress-bar").style.width = "100%";
  $(".progress-text").innerHTML = "";

  // Insert done banner before the list
  let banner = $(".done-banner");
  if (!banner) {
    banner = document.createElement("div");
    banner.className = "done-banner";
    $(".progress-section").after(banner);
  }
  banner.innerHTML = `
    <div class="done-stats">
      <div class="done-stat">
        <span class="done-num" style="color:var(--lime)">${successes}</span>
        <span class="done-label">Unfollowed</span>
      </div>
      <div class="done-stat">
        <span class="done-num" style="color:var(--amber)">${skipped}</span>
        <span class="done-label">Skipped</span>
      </div>
      <div class="done-stat">
        <span class="done-num" style="color:var(--red)">${errors}</span>
        <span class="done-label">Errors</span>
      </div>
    </div>
  `;

  // Update footer
  $(".unfollow-section").innerHTML = `
    <span class="selected-count">Done</span>
    <button class="btn btn-primary" onclick="location.reload()">Run Again</button>
  `;

  renderUserList();
}
