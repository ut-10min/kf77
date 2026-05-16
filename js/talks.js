function formatScheduleForTalk(schedule, talkId) {
  return schedule
    .filter((item) => item.talkId === talkId)
    .map((item) => `${item.dateLabel} ${item.start}–${item.end}`)
    .join("、");
}

function createTalkCard(talk, scheduleText) {
  const article = document.createElement("article");
  article.className = "talk-card";
  article.id = talk.id;

  article.innerHTML = `
    <h3>${talk.title}</h3>
    <p class="talk-meta"><b>${talk.speaker}</b>｜${talk.affiliation}｜${talk.field}</p>
    <p>${talk.description || "講演概要は準備中です。"}</p>
    <p class="talk-schedule"><b>登壇予定：</b>${scheduleText || "調整中"}</p>
  `;

  return article;
}

async function renderTalks() {
  const container = document.getElementById("talks-list");
  if (!container) return;

  try {
    const [talks, schedule] = await Promise.all([
      loadJson("data/talks.json"),
      loadJson("data/schedule.json")
    ]);

    container.innerHTML = "";
    const sortedTalks = [...talks].sort((a, b) =>
      (a.speakerKana || a.speaker || "").localeCompare(
        b.speakerKana || b.speaker || "",
        "ja"
      )
    );

    sortedTalks.forEach((talk) => {
      const scheduleText = formatScheduleForTalk(schedule, talk.id);
      container.appendChild(createTalkCard(talk, scheduleText));
    });
  } catch (error) {
    console.error(error);
    container.innerHTML = '<p class="section-note">講演情報を読み込めませんでした。</p>';
  }
}

document.addEventListener("DOMContentLoaded", renderTalks);
