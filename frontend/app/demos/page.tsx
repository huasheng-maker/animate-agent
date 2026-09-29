import styles from "./page.module.css";

const demos = [
  { id: "lidar", number: "01", category: "机器人 · 交互实验", title: "看见障碍，然后绕过去",
    description: "从激光回波到安全空间，再到路径搜索。改变货架位置和机器人半径，观察路线为什么改变。",
    href: "/demos/lidar", image: "/demos/lidar.png", origin: "确定性物理与路径规划实验",
    concepts: ["激光测距", "安全膨胀", "A* 搜索"] },
  { id: "circular-motion", number: "02", category: "物理 · 运动学", title: "速度在转，加速度指向哪里？",
    description: "跟随圆周上的质点，看清切向速度和向心加速度。改变运动参数，用画面检验直觉。",
    href: "/player?spec=/demos/circular-motion.json", image: "/demos/circular-motion.png",
    origin: "真实模型生成 · 本地审核", concepts: ["质点", "速度矢量", "向心加速度"] },
  { id: "llm", number: "03", category: "人工智能 · 计算过程", title: "一句话，是怎样生成的？",
    description: "从 token 到数值向量，再到下一 token 的概率。观察具体数据怎样改变，而不只是记住模块名称。",
    href: "/player?spec=/demos/llm.json", image: "/demos/llm.png",
    origin: "真实模型生成 · 本地审核", concepts: ["Embedding", "概率分布", "自回归"] },
];

export default function DemoGallery() {
  return <main className={styles.shell}>
    <nav className={styles.nav}><a href="/">ANIMATE / AGENT</a><span>可交互的知识实验室</span></nav>
    <header className={styles.header}>
      <p className={styles.kicker}>WATCH · CHANGE · UNDERSTAND</p>
      <h1>让原理<br /><em>发生在眼前。</em></h1>
      <p>选择一个问题，观察变化，再亲手改变一个条件。<br />三个示例均可直接体验，无需 API 密钥。</p>
    </header>
    <section className={styles.grid} aria-label="教学示例">
      {demos.map(demo => <a className={styles.card} href={demo.href} key={demo.id}>
        <div className={styles.preview}>
          {/* Local reviewed screenshots; no remote assets or image service. */}
          <img src={demo.image} alt={`${demo.title}的实际动画画面`} />
          <span className={styles.number}>{demo.number}</span>
        </div>
        <div className={styles.content}>
          <p className={styles.category}>{demo.category}</p>
          <h2>{demo.title}</h2><p className={styles.description}>{demo.description}</p>
          <div className={styles.concepts}>{demo.concepts.map(c => <span key={c}>{c}</span>)}</div>
          <div className={styles.footer}><small>{demo.origin}</small><strong>进入实验 ↗</strong></div>
        </div>
      </a>)}
    </section>
    <footer className={styles.bottom}><span>示例中的数值模型用于教学，不代表真实设备或完整生产模型。</span>
      <a href="/">提出自己的问题 →</a></footer>
  </main>;
}
