function groupBy(array, keyFn) {
  return array.reduce((acc, item) => {
    const key = keyFn(item);
    if (!acc[key]) acc[key] = [];
    acc[key].push(item);
    return acc;
  }, {});
}

function makeTalkMap(talks) {
  return talks.reduce((acc, talk) => {
    acc[talk.id] = talk;
    return acc;
  }, {});
}

function timeToMinutes(value) {
  const [hour, minute] = value.split(":").map(Number);
  return hour * 60 + minute;
}

function durationMinutes(item) {
  return Math.max(0, timeToMinutes(item.end) - timeToMinutes(item.start));
}

function durationLabel(item) {
  return `${durationMinutes(item)}分`;
}

function slotContent(item, talkMap) {
  const minutes = durationMinutes(item);
  const isLong = minutes >= 50;
  const durationClass = isLong ? " is-long-slot" : "";

  if (!item) {
    return "";
  }

  if (item.type === "break") {
    return `
      <div class="slot-card break-slot-card${durationClass}">
        <span class="duration-badge">${durationLabel(item)}</span>
        <div class="break-slot">${item.title || "休憩"}</div>
      </div>
    `;
  }

  const talk = talkMap[item.talkId];
  if (!talk) {
    return `
      <div class="slot-card slot-detail-card${durationClass}">
        <span class="duration-badge">${durationLabel(item)}</span>
        <div class="break-slot">講演情報未設定</div>
      </div>
    `;
  }

  return `
    <div class="slot-card slot-detail-card${durationClass}">
      <span class="duration-badge">${durationLabel(item)}</span>
      <div class="slot-detail-inner">
        <button class="talk-toggle" type="button" aria-expanded="false" aria-label="${talk.title} の詳細を開く">
          <span class="slot-detail-title">${talk.title}</span>
          <span class="slot-detail-speaker"><b>講演者：</b>${talk.speaker}</span>
          <span class="slot-open-label">詳細を開く</span>
        </button>
        <div class="slot-detail" role="region" aria-label="${talk.title} の講演詳細">
          <p class="slot-detail-affiliation"><b>所属・専攻：</b>${talk.affiliation}｜${talk.field}</p>
          <p class="slot-detail-abstract"><b>要旨：</b>${talk.description}</p>
        </div>
      </div>
    </div>
  `;
}

function renderDesktop(schedule, talkMap) {
  const desktop = document.getElementById("timetable-desktop");
  if (!desktop) return;

  const days = [...new Map(schedule.map((item) => [item.date, item.dateLabel])).entries()];
  const times = [...new Set(schedule.map((item) => `${item.start}-${item.end}`))].sort();

  const byDateTime = new Map();
  schedule.forEach((item) => {
    byDateTime.set(`${item.date}|${item.start}-${item.end}`, item);
  });

  const thead = `
    <thead>
      <tr>
        <th>時間</th>
        ${days.map(([, label]) => `<th>${label}</th>`).join("")}
      </tr>
    </thead>
  `;

  const tbody = `
    <tbody>
      ${times.map((time) => `
        <tr>
          <th>${time.replace("-", "–")}</th>
          ${days.map(([date]) => {
            const item = byDateTime.get(`${date}|${time}`);
            return `<td>${item ? slotContent(item, talkMap) : ""}</td>`;
          }).join("")}
        </tr>
      `).join("")}
    </tbody>
  `;

  desktop.innerHTML = `<table class="timetable-table timetable-table-enhanced">${thead}${tbody}</table>`;
}

function renderMobile(schedule, talkMap) {
  const tabs = document.getElementById("day-tabs");
  const mobile = document.getElementById("timetable-mobile");
  if (!tabs || !mobile) return;

  const grouped = groupBy(schedule, (item) => item.date);
  const days = Object.keys(grouped).map((date) => ({
    date,
    label: grouped[date][0].dateLabel
  }));

  tabs.innerHTML = "";
  mobile.innerHTML = "";

  days.forEach((day, index) => {
    const tab = document.createElement("button");
    tab.type = "button";
    tab.textContent = day.label;
    tab.setAttribute("aria-selected", index === 0 ? "true" : "false");
    tab.dataset.date = day.date;
    tabs.appendChild(tab);

    const panel = document.createElement("div");
    panel.className = "mobile-day-panel";
    panel.dataset.date = day.date;
    if (index !== 0) panel.hidden = true;

    const items = grouped[day.date].sort((a, b) => `${a.start}-${a.end}`.localeCompare(`${b.start}-${b.end}`));
    panel.innerHTML = items.map((item) => `
      <article class="mobile-slot">
        <div class="mobile-time">${item.start}–${item.end}</div>
        ${slotContent(item, talkMap)}
      </article>
    `).join("");

    mobile.appendChild(panel);
  });

  tabs.addEventListener("click", (event) => {
    const button = event.target.closest("button[data-date]");
    if (!button) return;

    tabs.querySelectorAll("button").forEach((btn) => {
      btn.setAttribute("aria-selected", btn === button ? "true" : "false");
    });

    mobile.querySelectorAll(".mobile-day-panel").forEach((panel) => {
      panel.hidden = panel.dataset.date !== button.dataset.date;
    });
  });
}

function setupDetailsToggle() {
  document.addEventListener("click", (event) => {
    const button = event.target.closest(".talk-toggle");
    if (!button) return;

    const detail = button.parentElement.querySelector(".slot-detail");
    const label = button.querySelector(".slot-open-label");
    const isOpen = detail.classList.toggle("is-open");
    button.setAttribute("aria-expanded", isOpen ? "true" : "false");
    if (label) label.textContent = isOpen ? "詳細を閉じる" : "詳細を開く";
  });
}

async function renderTimetable() {
  try {
    const [talks, schedule] = await Promise.all([
      loadJson("data/talks.json"),
      loadJson("data/schedule.json")
    ]);

    schedule.sort((a, b) => `${a.date} ${a.start}`.localeCompare(`${b.date} ${b.start}`));
    const talkMap = makeTalkMap(talks);

    renderDesktop(schedule, talkMap);
    renderMobile(schedule, talkMap);
    setupDetailsToggle();
  } catch (error) {
    console.error(error);
    const desktop = document.getElementById("timetable-desktop");
    if (desktop) desktop.innerHTML = '<p class="section-note">タイムテーブルを読み込めませんでした。</p>';
  }
}

document.addEventListener("DOMContentLoaded", renderTimetable);
