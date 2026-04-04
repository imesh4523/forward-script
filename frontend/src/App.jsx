import { useState, useEffect } from 'react'
import { Toaster, toast } from 'react-hot-toast'
import {
  Settings, Send, Activity, Save, Plus, Trash2, Play, Square,
  CheckCircle, XCircle, Loader, Bot, RefreshCw, ChevronRight,
  Search, UserPlus, Clock, Eye, ToggleLeft, ToggleRight,
  Image, ExternalLink, Rocket
} from 'lucide-react'
import axios from 'axios'

const API = window.location.origin.includes('localhost:5173') 
  ? 'http://localhost:8001/api' 
  : window.location.origin + '/api'

const glassStyle = {
  background: 'rgba(30, 41, 59, 0.5)',
  backdropFilter: 'blur(12px)',
  border: '1px solid rgba(51, 65, 85, 0.5)',
  borderRadius: '1rem',
}

/* ========== SIDEBAR ========== */
function Sidebar({ activeTab, setActiveTab, botStatus, onStart, onStop }) {
  const navItems = [
    { id: 'settings', label: 'Config & API', icon: Settings, activeClass: 'bg-blue-600/20 text-blue-400 border-blue-500/20' },
    { id: 'groups', label: 'Target Groups', icon: Send, activeClass: 'bg-indigo-600/20 text-indigo-400 border-indigo-500/20' },
    { id: 'autojoin', label: 'Auto-Join Manager', icon: UserPlus, activeClass: 'bg-violet-600/20 text-violet-400 border-violet-500/20' },
    { id: 'custom', label: 'Custom Message', icon: Rocket, activeClass: 'bg-rose-600/20 text-rose-400 border-rose-500/20' },
    { id: 'test', label: 'Test & Debug', icon: CheckCircle, activeClass: 'bg-emerald-600/20 text-emerald-400 border-emerald-500/20' },
    { id: 'status', label: 'Live Status', icon: Activity, activeClass: 'bg-cyan-600/20 text-cyan-400 border-cyan-500/20' },
  ]

  return (
    <aside className="w-64 shrink-0 flex flex-col gap-4 h-screen sticky top-0 p-6">
      <div className="flex items-center gap-3 mb-6">
        <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-blue-500 to-indigo-600 flex items-center justify-center" style={{ boxShadow: '0 8px 24px rgba(59,130,246,0.3)' }}>
          <Bot size={20} className="text-white" />
        </div>
        <div>
          <h1 className="font-bold text-base text-white leading-tight">Auto Forwarder</h1>
          <p className="text-xs text-slate-500">Telegram Bot</p>
        </div>
      </div>

      <div className={`flex items-center gap-2 px-3 py-2 rounded-lg text-xs font-medium border ${
        botStatus === 'running' ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20' : 'bg-slate-700/30 text-slate-400 border-slate-700/50'
      }`}>
        <span className={`w-2 h-2 rounded-full ${botStatus === 'running' ? 'bg-emerald-400 animate-pulse' : 'bg-slate-500'}`}></span>
        {botStatus === 'running' ? 'Bot Running' : 'Bot Stopped'}
      </div>

      <nav className="flex flex-col gap-1 flex-1 mt-2">
        {navItems.map(({ id, label, icon: Icon, activeClass }) => (
          <button key={id} onClick={() => setActiveTab(id)}
            className={`flex items-center gap-3 px-4 py-3 rounded-xl text-sm transition-all duration-200 border cursor-pointer ${
              activeTab === id ? activeClass : 'hover:bg-slate-700/30 text-slate-400 border-transparent'
            }`}>
            <Icon size={17} />
            <span className="font-medium">{label}</span>
            {activeTab === id && <ChevronRight size={14} className="ml-auto" />}
          </button>
        ))}
      </nav>

      <div className="pt-4 border-t border-slate-700/50">
        {botStatus === 'running' ? (
          <button onClick={onStop} className="w-full flex items-center justify-center gap-2 bg-red-500/10 text-red-400 border border-red-500/25 py-3 rounded-xl hover:bg-red-500/20 transition-all font-medium text-sm cursor-pointer">
            <Square size={15} /> Stop Bot
          </button>
        ) : (
          <button onClick={onStart} className="w-full flex items-center justify-center gap-2 bg-emerald-500/10 text-emerald-400 border border-emerald-500/25 py-3 rounded-xl hover:bg-emerald-500/20 transition-all font-medium text-sm cursor-pointer"
            style={{ boxShadow: '0 8px 24px rgba(16,185,129,0.08)' }}>
            <Play size={15} /> Start Bot
          </button>
        )}
      </div>
    </aside>
  )
}

/* ========== AUTH PANEL (reusable) ========== */
function AuthPanel({ title, configUrl, authUrl, verifyUrl }) {
  const [form, setForm] = useState({ api_id: '', api_hash: '', phone_number: '' })
  const [authStatus, setAuthStatus] = useState(false)
  const [isLive, setIsLive] = useState(false)
  const [loading, setLoading] = useState(false)
  const [otpSent, setOtpSent] = useState(false)
  const [otp, setOtp] = useState('')
  const [password, setPassword] = useState('')
  const [needsPassword, setNeedsPassword] = useState(false)
  const [checking, setChecking] = useState(false)

  const checkLiveStatus = async () => {
    setChecking(true)
    const liveUrl = authUrl.includes('sender') ? 'sender-auth/live' : 'auth/live'
    try {
      const res = await axios.get(`${API}/${liveUrl}`)
      setIsLive(res.data.live)
      // Only mark as fully not-authenticated if the backend says so AND we were already authenticated
      if (!res.data.live) {
        // We don't force authStatus false immediately to allow retries/refresh
        // toast.error('Session seems dead or disconnected')
      }
    } catch {
      toast.error('Check failed')
    } finally {
      setChecking(false)
    }
  }

  useEffect(() => {
    axios.get(`${API}/${configUrl}`).then(r => {
      setForm(prev => ({ ...prev, ...r.data }))
      setAuthStatus(r.data.is_authenticated)
      
      if (r.data.is_authenticated) {
        checkLiveStatus()
      }
    }).catch(() => {})
  }, [configUrl, authUrl])

  const saveConfig = async () => {
    setLoading(true)
    try {
      await axios.post(`${API}/${configUrl}`, form)
      setAuthStatus(false)
      setIsLive(false)
      setOtpSent(false)
      toast.success('Config saved!')
    } catch { toast.error('Failed to save') }
    finally { setLoading(false) }
  }

  const logout = async () => {
    setLoading(true)
    const logoutUrl = authUrl.includes('sender') ? 'sender-auth/logout' : 'auth/logout'
    try {
      await axios.post(`${API}/${logoutUrl}`)
      setAuthStatus(false)
      setIsLive(false)
      toast.success('Account removed/logged out')
    } catch { toast.error('Failed to logout') }
    finally { setLoading(false) }
  }

  const sendOtp = async () => {
    setLoading(true)
    try {
      const res = await axios.post(`${API}/${authUrl}`)
      if (res.data.already_authenticated) {
        setAuthStatus(true)
        setIsLive(true)
        setOtpSent(false)
        toast.success('Found existing session! Logged in ✅')
      } else {
        setOtpSent(true)
        toast.success('OTP sent to Telegram!')
      }
    } catch (e) { toast.error(e.response?.data?.detail || 'Failed to send OTP') }
    finally { setLoading(false) }
  }

  const verifyOtp = async () => {
    setLoading(true)
    try {
      const res = await axios.post(`${API}/${verifyUrl}`, { code: otp, password: password || null })
      if (res.data.status === 'needs_password') {
        setNeedsPassword(true)
        toast('2FA Password required', { icon: '🔐' })
      } else {
        setAuthStatus(true)
        setIsLive(true)
        setOtpSent(false)
        toast.success('Logged in! ✅')
      }
    } catch (e) { toast.error(e.response?.data?.detail || 'Wrong code') }
    finally { setLoading(false) }
  }

  const inputClass = "w-full bg-slate-900/60 border border-slate-700 rounded-xl px-4 py-3 text-slate-200 text-sm outline-none focus:border-blue-500 transition-all"

  return (
    <div className="bg-slate-900/40 rounded-2xl border border-slate-700/50 p-6 space-y-5">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-bold text-slate-200">{title}</h3>
        <button onClick={saveConfig} disabled={loading}
          className="flex items-center gap-1.5 bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white px-4 py-2 rounded-lg transition-all font-medium text-xs cursor-pointer">
          {loading ? <Loader size={13} className="animate-spin" /> : <Save size={13} />} Save Config
        </button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
        <div>
          <label className="block text-xs font-semibold text-slate-500 mb-1 uppercase tracking-wider">API ID</label>
          <input type="text" value={form.api_id} onChange={e => setForm(p => ({ ...p, api_id: e.target.value }))} placeholder="12345678" className={inputClass} />
        </div>
        <div>
          <label className="block text-xs font-semibold text-slate-500 mb-1 uppercase tracking-wider">API Hash</label>
          <input type="text" value={form.api_hash} onChange={e => setForm(p => ({ ...p, api_hash: e.target.value }))} placeholder="a1b2c3d4..." className={inputClass} />
        </div>
        <div>
          <label className="block text-xs font-semibold text-slate-500 mb-1 uppercase tracking-wider">Phone</label>
          <input type="text" value={form.phone_number} onChange={e => setForm(p => ({ ...p, phone_number: e.target.value }))} placeholder="+9477XXXXXXX" className={inputClass} />
        </div>
      </div>

      {/* Auth Status */}
      <div className="flex items-center gap-3">
        {authStatus ? (
          <>
            <div className={`flex items-center gap-2 text-sm px-3 py-2 rounded-lg border flex-1 ${isLive ? 'text-emerald-400 bg-emerald-500/10 border-emerald-500/20' : 'text-amber-400 bg-amber-500/10 border-amber-500/20'}`}>
              {isLive ? <Activity size={16} /> : <XCircle size={16} />} 
              {isLive ? 'Live & Authenticated ✅' : 'Session Status Unknown / Re-check'}
              <button onClick={checkLiveStatus} disabled={checking} className="ml-auto hover:bg-white/10 p-1 rounded-md transition-colors">
                <RefreshCw size={14} className={checking ? 'animate-spin' : ''} />
              </button>
            </div>
            <button onClick={logout} disabled={loading} className="flex items-center justify-center gap-1.5 bg-red-600/10 hover:bg-red-500/30 text-red-500 border border-red-500/20 px-4 py-2 rounded-lg text-xs font-semibold transition-all cursor-pointer disabled:opacity-50">
             {loading ? <Loader size={14} className="animate-spin" /> : <Trash2 size={14} />} Remove Account
            </button>
          </>
        ) : (
          <>
            <div className="flex items-center gap-2 text-amber-400 text-xs bg-amber-500/10 px-3 py-2 rounded-lg border border-amber-500/20">
              <XCircle size={14} /> Not authenticated
            </div>
            {!otpSent ? (
              <button onClick={sendOtp} disabled={loading || !form.api_id}
                className="flex items-center gap-1.5 bg-white text-slate-900 px-4 py-2 rounded-lg text-xs font-medium hover:bg-slate-200 transition-colors disabled:opacity-50 cursor-pointer">
                {loading ? <Loader size={13} className="animate-spin" /> : null} Request OTP
              </button>
            ) : (
              <div className="flex gap-2 flex-1">
                <input type="text" placeholder="OTP Code" value={otp} onChange={e => setOtp(e.target.value)}
                  className="flex-1 bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-slate-200 text-sm outline-none focus:border-blue-500" />
                {needsPassword && (
                  <input type="password" placeholder="2FA Pass" value={password} onChange={e => setPassword(e.target.value)}
                    className="w-28 bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-slate-200 text-sm outline-none focus:border-blue-500" />
                )}
                <button onClick={verifyOtp} disabled={loading || !otp}
                  className="bg-blue-600 hover:bg-blue-500 text-white px-4 py-2 rounded-lg text-xs font-medium transition-all disabled:opacity-50 cursor-pointer">
                  {loading ? '...' : 'Verify'}
                </button>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  )
}

/* ========== SETTINGS TAB ========== */
function SettingsTab() {
  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-bold text-white flex items-center gap-3">
          <Settings className="text-blue-400" size={24} /> Telegram Configuration
        </h2>
        <p className="text-slate-400 mt-1 text-sm">Configure both accounts. Get credentials from my.telegram.org</p>
      </div>

      <AuthPanel
        title="👁️ Source Account (Channel Watcher)"
        configUrl="config"
        authUrl="auth/send_code"
        verifyUrl="auth/verify"
      />

      <AuthPanel
        title="📤 Sender Account (Message Sender)"
        configUrl="sender-config"
        authUrl="sender-auth/send_code"
        verifyUrl="sender-auth/verify"
      />
    </div>
  )
}

/* ========== GROUPS TAB ========== */
function GroupsTab() {
  const [groups, setGroups] = useState([])
  const [newGroup, setNewGroup] = useState('')
  const [postLink, setPostLink] = useState('')
  const [delayMin, setDelayMin] = useState(30)
  const [delayMax, setDelayMax] = useState(120)
  const [hourlyCount, setHourlyCount] = useState(3)
  const [joinDelay, setJoinDelay] = useState(60)
  const [cycleRest, setCycleRest] = useState(3)
  const [totalSent, setTotalSent] = useState(0)
  const [loading, setLoading] = useState(false)
  const [detecting, setDetecting] = useState(false)
  const [joinLinks, setJoinLinks] = useState('')

  useEffect(() => {
    axios.get(`${API}/groups`).then(r => setGroups(r.data.groups || [])).catch(() => {})
    axios.get(`${API}/forwarding-config`).then(r => {
      if (r.data) {
        setPostLink(r.data.post_link || '')
        setDelayMin(r.data.delay_min || 30)
        setDelayMax(r.data.delay_max || 120)
        setHourlyCount(r.data.hourly_count || 3)
        setJoinDelay(r.data.join_delay_minutes || 60)
        setCycleRest(r.data.cycle_rest_minutes || 3)
        setTotalSent(r.data.total_sent_count || 0)
      }
    }).catch(() => {})
  }, [])

  const autoDetect = async () => {
    setDetecting(true)
    try {
      const res = await axios.post(`${API}/groups/auto-detect`)
      toast.success(`Detected ${res.data.count} groups from Source!`)
      const r = await axios.get(`${API}/groups`)
      setGroups(r.data.groups || [])
    } catch (e) { toast.error(e.response?.data?.detail || 'Detection failed') }
    finally { setDetecting(false) }
  }

  const addGroup = async () => {
    if (!newGroup.trim()) return
    setLoading(true)
    try {
      const res = await axios.post(`${API}/groups`, { group_id_or_username: newGroup.trim() })
      setGroups(p => [...p, { id: res.data.id || Date.now(), group_id_or_username: newGroup.trim(), group_title: newGroup.trim(), is_joined: false, is_selected: true }])
      setNewGroup('')
      toast.success('Group added!')
    } catch { toast.error('Failed') }
    finally { setLoading(false) }
  }

  const deleteGroup = async (id) => {
    try {
      await axios.delete(`${API}/groups/${id}`)
      setGroups(p => p.filter(g => g.id !== id))
      toast.success('Removed')
    } catch { toast.error('Failed') }
  }

  const toggleSelect = async (id, current) => {
    try {
      await axios.patch(`${API}/groups/${id}/select`, { is_selected: !current })
      setGroups(p => p.map(g => g.id === id ? { ...g, is_selected: !current } : g))
    } catch { toast.error('Failed') }
  }

  const saveForwardConfig = async () => {
    try {
      await axios.post(`${API}/forwarding-config`, { 
        post_link: postLink, 
        delay_min: delayMin, 
        delay_max: delayMax, 
        hourly_count: hourlyCount, 
        join_delay_minutes: joinDelay,
        cycle_rest_minutes: cycleRest,
        total_sent_count: totalSent
      })
      toast.success('Settings saved!')
    } catch { toast.error('Failed') }
  }

  const autoJoin = async () => {
    const links = joinLinks.split('\n').map(l => l.trim()).filter(Boolean)
    if (!links.length) return toast.error('Enter group links')
    try {
      await axios.post(`${API}/groups/auto-join`, { group_links: links })
      toast.success(`Started joining ${links.length} groups!`)
      setJoinLinks('')
    } catch (e) { toast.error(e.response?.data?.detail || 'Failed') }
  }

  const inputClass = "w-full bg-slate-800 border border-slate-700 rounded-xl px-4 py-3 text-slate-200 text-sm outline-none focus:border-indigo-500 transition-all"
  const selectedCount = groups.filter(g => g.is_selected).length

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold text-white flex items-center gap-3">
            <Send className="text-indigo-400" size={24} /> Target Groups
          </h2>
          <p className="text-slate-400 mt-1 text-sm">Manage groups for message forwarding</p>
        </div>
        <div className="flex items-center gap-4">
          <div className="bg-emerald-500/5 px-4 py-2 rounded-xl border border-emerald-500/20 flex flex-col items-end shadow-inner h-full justify-center">
            <span className="text-[10px] text-emerald-500/60 uppercase tracking-widest font-bold">Total Sent</span>
            <span className="text-lg font-black text-emerald-400 leading-tight">{totalSent}</span>
          </div>
          <button onClick={autoDetect} disabled={detecting}
            className="flex items-center gap-2 bg-violet-600 hover:bg-violet-500 disabled:opacity-50 text-white px-4 py-2.5 rounded-xl transition-all font-medium text-sm cursor-pointer"
            style={{ boxShadow: '0 4px 16px rgba(139,92,246,0.25)' }}>
            {detecting ? <Loader size={15} className="animate-spin" /> : <Search size={15} />}
            Auto-Detect Groups
          </button>
        </div>
      </div>

      {/* Forwarding Settings */}
      <div className="bg-slate-900/40 rounded-2xl border border-slate-700/50 p-5 space-y-4">
        <h3 className="text-sm font-semibold text-slate-300 flex items-center gap-2"><Clock size={15} /> Forwarding Settings</h3>
        <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
          <div className="col-span-2 md:col-span-5">
            <label className="block text-xs font-semibold text-slate-500 mb-1 uppercase tracking-wider">Telegram Post Link</label>
            <input type="text" value={postLink} onChange={e => setPostLink(e.target.value)}
              placeholder="https://t.me/imesh_cloud_official/16" className={inputClass} />
          </div>
          <div>
            <label className="block text-xs font-semibold text-slate-500 mb-1 uppercase tracking-wider">Min Delay (s)</label>
            <input type="number" value={delayMin} onChange={e => setDelayMin(Number(e.target.value))} min={5} className={inputClass} />
          </div>
          <div>
            <label className="block text-xs font-semibold text-slate-500 mb-1 uppercase tracking-wider">Max Delay (s)</label>
            <input type="number" value={delayMax} onChange={e => setDelayMax(Number(e.target.value))} min={10} className={inputClass} />
          </div>
          <div>
            <label className="block text-xs font-semibold text-slate-500 mb-1 uppercase tracking-wider">Hourly Count</label>
            <input type="number" value={hourlyCount} onChange={e => setHourlyCount(Number(e.target.value))} min={1} className={inputClass} />
          </div>
          <div>
            <label className="block text-xs font-semibold text-slate-500 mb-1 uppercase tracking-wider">Cycle Rest (min)</label>
            <input type="number" value={cycleRest} onChange={e => setCycleRest(Number(e.target.value))} min={1} className={inputClass} />
          </div>
          <div className="flex items-end">
            <button onClick={saveForwardConfig}
              className="w-full bg-indigo-600 hover:bg-indigo-500 text-white py-3 rounded-xl font-medium text-sm transition-all cursor-pointer">
              Save
            </button>
          </div>
              className="w-full bg-indigo-600 hover:bg-indigo-500 text-white py-3 rounded-xl font-medium text-sm transition-all cursor-pointer">
              Save
            </button>
          </div>
        </div>
      </div>

      {/* Auto Join */}
      <div className="bg-slate-900/40 rounded-2xl border border-slate-700/50 p-5 space-y-3">
        <h3 className="text-sm font-semibold text-slate-300 flex items-center gap-2"><UserPlus size={15} /> Auto-Join New Groups</h3>
        <p className="text-xs text-slate-500">Paste group links (one per line). Sender account will join them with rate limiting.</p>
        <textarea value={joinLinks} onChange={e => setJoinLinks(e.target.value)} rows={3}
          placeholder={"https://t.me/group1\nhttps://t.me/+inviteHash\n@groupusername"}
          className="w-full bg-slate-800 border border-slate-700 rounded-xl px-4 py-3 text-slate-200 text-sm outline-none focus:border-indigo-500 transition-all resize-none" />
        <button onClick={autoJoin} className="flex items-center gap-2 bg-violet-600 hover:bg-violet-500 text-white px-5 py-2.5 rounded-xl font-medium text-sm transition-all cursor-pointer">
          <UserPlus size={15} /> Start Auto-Join
        </button>
      </div>

      {/* Add single group */}
      <div className="flex gap-3">
        <input type="text" value={newGroup} onChange={e => setNewGroup(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && addGroup()}
          placeholder="Add single group: @mygroup"
          className="flex-1 bg-slate-900/60 border border-slate-700 rounded-xl px-4 py-3 text-slate-200 text-sm outline-none focus:border-indigo-500 transition-all" />
        <button onClick={addGroup} disabled={loading || !newGroup.trim()}
          className="flex items-center gap-2 bg-indigo-600 hover:bg-indigo-500 text-white px-5 py-3 rounded-xl transition-all font-medium text-sm disabled:opacity-50 cursor-pointer">
          <Plus size={16} /> Add
        </button>
      </div>

      {/* Groups list */}
      <div className="space-y-2">
        <div className="flex items-center justify-between text-xs text-slate-500 px-2">
          <span>{groups.length} groups total • {selectedCount} selected for forwarding</span>
        </div>
        {groups.length === 0 ? (
          <div className="text-center py-10 text-slate-500">
            <Send size={28} className="mx-auto mb-2 opacity-30" />
            <p className="text-sm">No groups yet. Use Auto-Detect or add manually.</p>
          </div>
        ) : (
          groups.map((g, i) => (
            <div key={g.id} className={`flex items-center gap-3 border rounded-xl px-4 py-3 transition-all ${
              g.is_selected ? 'bg-slate-800/40 border-slate-700/50' : 'bg-slate-800/20 border-slate-800/30 opacity-50'
            }`}>
              <span className="text-slate-500 text-xs w-5 text-center">{i + 1}</span>
              <button onClick={() => toggleSelect(g.id, g.is_selected)} className="cursor-pointer text-slate-400 hover:text-white transition-colors">
                {g.is_selected ? <ToggleRight size={20} className="text-emerald-400" /> : <ToggleLeft size={20} />}
              </button>
              <div className="flex-1 min-w-0">
                <p className="text-slate-300 text-sm font-medium truncate">{g.group_title || g.group_id_or_username}</p>
                <div className="flex items-center gap-2">
                  <p className="text-slate-500 text-[10px] font-mono truncate">{g.group_id_or_username}</p>
                  {g.is_sender_joined && (
                    <span className="flex items-center gap-1 text-[10px] text-violet-400 bg-violet-400/10 px-1.5 py-0.5 rounded border border-violet-400/20">
                      <UserPlus size={10} /> Sender Joined
                    </span>
                  )}
                </div>
              </div>
              <button onClick={() => deleteGroup(g.id)} className="text-slate-600 hover:text-red-400 transition-colors cursor-pointer p-2">
                <Trash2 size={15} />
              </button>
            </div>
          ))
        )}
      </div>
    </div>
  )
}

/* ========== AUTO-JOIN MANAGER TAB ========== */
function AutoJoinTab() {
  const [status, setStatus] = useState({ is_running: false, total_groups: 0, joined_groups: 0, pending_groups: 0 })
  const [loading, setLoading] = useState(false)
  const [joinDelay, setJoinDelay] = useState(60)

  const fetchStatus = async () => {
    try {
      const r = await axios.get(`${API}/bot/auto-join-status`)
      setStatus(r.data)
    } catch {}
  }

  useEffect(() => {
    fetchStatus()
    const timer = setInterval(fetchStatus, 5000)
    return () => clearInterval(timer)
  }, [])

  useEffect(() => {
    axios.get(`${API}/forwarding-config`).then(r => {
      if (r.data) setJoinDelay(r.data.join_delay_minutes || 60)
    }).catch(() => {})
  }, [])

  const startAutoJoin = async () => {
    setLoading(true)
    try {
      await axios.post(`${API}/bot/start-auto-join`)
      toast.success('Auto-Join Manager started!')
      fetchStatus()
    } catch (e) { toast.error(e.response?.data?.detail || 'Failed to start') }
    finally { setLoading(false) }
  }

  const stopAutoJoin = async () => {
    setLoading(true)
    try {
      await axios.post(`${API}/bot/stop-auto-join`)
      toast('Auto-Join stopped', { icon: '🛑' })
      fetchStatus()
    } catch { toast.error('Failed to stop') }
    finally { setLoading(false) }
  }

  const saveJoinDelay = async () => {
    try {
      const current = await axios.get(`${API}/forwarding-config`)
      await axios.post(`${API}/forwarding-config`, { ...current.data, join_delay_minutes: joinDelay })
      toast.success('Join delay updated!')
    } catch { toast.error('Failed to save') }
  }

  const progress = status.total_groups > 0 ? (status.joined_groups / status.total_groups) * 100 : 0

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-bold text-white flex items-center gap-3">
          <UserPlus className="text-violet-400" size={24} /> Auto-Join Manager
        </h2>
        <p className="text-slate-400 mt-1 text-sm">Background system to automatically join your Sender account to Source groups (1 per hour).</p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="bg-slate-900/40 rounded-2xl border border-slate-700/50 p-5 flex flex-col items-center justify-center text-center">
          <span className="text-slate-500 text-xs font-semibold uppercase tracking-wider mb-1">Total Groups (Source)</span>
          <span className="text-3xl font-bold text-white">{status.total_groups}</span>
        </div>
        <div className="bg-emerald-500/5 rounded-2xl border border-emerald-500/20 p-5 flex flex-col items-center justify-center text-center">
          <span className="text-emerald-500/60 text-xs font-semibold uppercase tracking-wider mb-1">Sender Joined</span>
          <span className="text-3xl font-bold text-emerald-400">{status.joined_groups}</span>
        </div>
        <div className="bg-violet-500/5 rounded-2xl border border-violet-500/20 p-5 flex flex-col items-center justify-center text-center">
          <span className="text-violet-500/60 text-xs font-semibold uppercase tracking-wider mb-1">Remaining to Join</span>
          <span className="text-3xl font-bold text-violet-400">{status.pending_groups}</span>
        </div>
      </div>

      <div className="bg-slate-900/40 rounded-2xl border border-slate-700/50 p-6 space-y-6">
        <div className="space-y-2">
          <div className="flex justify-between text-xs font-medium">
            <span className="text-slate-400">Joining Progress</span>
            <span className="text-violet-400">{Math.round(progress)}%</span>
          </div>
          <div className="w-full bg-slate-800 rounded-full h-2 overflow-hidden border border-slate-700/50">
            <div className="bg-gradient-to-r from-violet-600 to-indigo-500 h-full transition-all duration-1000" style={{ width: `${progress}%` }}></div>
          </div>
        </div>

        <div className="flex flex-col md:flex-row gap-4 items-end pt-2">
          <div className="flex-1 text-left">
            <label className="block text-xs font-semibold text-slate-500 mb-2 uppercase tracking-wider">Join Speed (Minutes per group)</label>
            <div className="flex gap-2">
              <input type="number" value={joinDelay} onChange={e => setJoinDelay(Number(e.target.value))} min={1}
                className="flex-1 bg-slate-800 border border-slate-700 rounded-xl px-4 py-3 text-slate-200 text-sm outline-none focus:border-violet-500 transition-all" />
              <button onClick={saveJoinDelay} className="bg-slate-700 hover:bg-slate-600 text-white px-4 py-2 rounded-xl text-xs font-medium transition-all cursor-pointer">
                Set
              </button>
            </div>
          </div>
          <div className="flex-1 w-full">
            {status.is_running ? (
              <button onClick={stopAutoJoin} disabled={loading}
                className="w-full bg-red-500/10 hover:bg-red-500/20 text-red-500 border border-red-500/30 py-3.5 rounded-xl font-bold text-sm flex items-center justify-center gap-2 transition-all cursor-pointer">
                <Square size={16} /> Stop Auto-Joiner
              </button>
            ) : (
              <button onClick={startAutoJoin} disabled={loading || status.pending_groups === 0}
                className="w-full bg-violet-600 hover:bg-violet-500 text-white py-3.5 rounded-xl font-bold text-sm flex items-center justify-center gap-2 transition-all shadow-lg shadow-violet-600/20 disabled:opacity-50 cursor-pointer">
                <Play size={16} /> Start Auto-Joiner
              </button>
            )}
          </div>
        </div>
        
        <div className={`flex items-center gap-2 px-4 py-3 rounded-xl border text-xs font-medium ${
          status.is_running ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20' : 'bg-slate-800/50 text-slate-500 border-slate-700/50'
        }`}>
          {status.is_running ? (
            <><Activity size={14} className="animate-pulse" /> Auto-Join Manager is active and working in background.</>
          ) : (
            <><XCircle size={14} /> Auto-Join Manager is currently idle.</>
          )}
        </div>
      </div>

      {/* Pending Groups List */}
      <div className="space-y-3">
        <h3 className="text-sm font-bold text-slate-300 flex items-center gap-2">
          <Clock size={16} className="text-violet-400" /> Pending Groups Queue ({status.pending_groups})
        </h3>
        <div className="bg-slate-900/40 rounded-2xl border border-slate-700/50 overflow-hidden">
          <div className="max-h-[300px] overflow-y-auto custom-scrollbar">
            {status.pending_list?.length === 0 ? (
              <div className="p-10 text-center text-slate-500 text-sm italic">
                No pending groups. All groups are already joined by the Sender account!
              </div>
            ) : (
              status.pending_list?.map((g, i) => (
                <div key={i} className="flex items-center justify-between px-5 py-3 border-b border-slate-700/30 hover:bg-slate-800/30 transition-colors">
                  <div className="flex items-center gap-3">
                    <span className="text-slate-600 text-[10px] w-4">{i + 1}</span>
                    <div>
                      <p className="text-slate-200 text-sm font-medium leading-tight">{g.group_title}</p>
                      <p className="text-slate-500 text-[10px] font-mono">{g.group_id_or_username}</p>
                    </div>
                  </div>
                  <span className="text-[10px] font-semibold text-violet-400/70 uppercase tracking-tighter">Waiting</span>
                </div>
              ))
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

/* ========== CUSTOM BROADCAST TAB ========== */
function CustomBroadcastTab() {
  const [text, setText] = useState('')
  const [targetGroup, setTargetGroup] = useState('')
  const [photo, setPhoto] = useState(null)
  const [photoPreview, setPhotoPreview] = useState(null)
  const [buttons, setButtons] = useState([{ label: '', url: '' }, { label: '', url: '' }, { label: '', url: '' }])
  const [botToken, setBotToken] = useState('')
  const [loading, setLoading] = useState(false)
  const [groups, setGroups] = useState([])

  useEffect(() => {
    axios.get(`${API}/groups`).then(r => setGroups(r.data.groups || [])).catch(() => {})
  }, [])

  const onPhotoChange = (e) => {
    const file = e.target.files[0]
    if (file) {
      setPhoto(file)
      setPhotoPreview(URL.createObjectURL(file))
    }
  }

  const updateButton = (i, field, val) => {
    const b = [...buttons]
    b[i][field] = val
    setButtons(b)
  }

  const sendCustom = async () => {
    if (!text || !targetGroup) return toast.error('Message & Target Group required')
    
    setLoading(true)
    const formData = new FormData()
    formData.append('test_group', targetGroup)
    formData.append('text', text)
    formData.append('buttons_json', JSON.stringify(buttons.filter(b => b.label && b.url)))
    if (botToken) formData.append('bot_token', botToken)
    if (photo) formData.append('photo', photo)

    try {
      const res = await axios.post(`${API}/bot/send-custom`, formData, {
        headers: { 'Content-Type': 'multipart/form-data' }
      })
      toast.success(res.data.message || 'Sent! 🚀')
      setText('')
      setPhoto(null)
      setPhotoPreview(null)
      setButtons([{ label: '', url: '' }, { label: '', url: '' }, { label: '', url: '' }])
    } catch (e) { toast.error(e.response?.data?.detail || 'Failed to send') }
    finally { setLoading(false) }
  }

  const inputClass = "w-full bg-slate-800 border border-slate-700/50 rounded-xl px-4 py-3 text-slate-200 text-sm outline-none focus:border-rose-500 transition-all placeholder:text-slate-600"

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-bold text-white flex items-center gap-3">
          <Rocket className="text-rose-400" size={24} /> Custom Broadcast
        </h2>
        <p className="text-slate-400 mt-1 text-sm">Send a personalized message with photo and buttons to any group.</p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Left: Editor */}
        <div className="space-y-5 bg-slate-900/40 rounded-2xl border border-slate-700/50 p-6">
          <div className="space-y-2 text-left">
            <label className="block text-xs font-semibold text-slate-500 uppercase tracking-wider">Target Group</label>
            <select value={targetGroup} onChange={e => setTargetGroup(e.target.value)} className={inputClass}>
              <option value="">-- Select Group --</option>
              {groups.map(g => (
                <option key={g.id} value={g.group_id_or_username}>{g.group_title || g.group_id_or_username}</option>
              ))}
            </select>
            <p className="text-[10px] text-slate-600 italic mt-1">Or type manually below</p>
            <input type="text" placeholder="@group_username or ID" value={targetGroup} onChange={e => setTargetGroup(e.target.value)} className={inputClass} />
          </div>

          <div className="space-y-2 text-left">
            <label className="block text-xs font-semibold text-slate-500 uppercase tracking-wider flex items-center gap-2">
              <Bot size={12} className="text-blue-400" /> Bot Token (Required for Buttons)
            </label>
            <input type="text" placeholder="123456789:ABCDefgh..." value={botToken} onChange={e => setBotToken(e.target.value)} className={inputClass} />
            <p className="text-[10px] text-slate-500 italic">Get from @BotFather. Bot MUST be in the target group.</p>
          </div>

          <div className="space-y-2 text-left">
            <label className="block text-xs font-semibold text-slate-500 uppercase tracking-wider">Message Caption (Text)</label>
            <textarea value={text} onChange={e => setText(e.target.value)} rows={4}
              placeholder="Type your message here..." className="w-full bg-slate-800 border border-slate-700/50 rounded-xl px-4 py-3 text-slate-200 text-sm outline-none focus:border-rose-500 transition-all resize-none" />
          </div>

          <div className="space-y-2 text-left">
            <label className="block text-xs font-semibold text-slate-500 uppercase tracking-wider">Add Photo (Optional)</label>
            <div className="flex items-center gap-3">
              <label className="flex-1 flex flex-col items-center justify-center border-2 border-dashed border-slate-700 rounded-xl p-4 hover:border-rose-500/50 transition-colors cursor-pointer group">
                <Image className="text-slate-500 group-hover:text-rose-400 mb-2" size={20} />
                <span className="text-xs text-slate-500 font-medium">Click to upload photo</span>
                <input type="file" accept="image/*" onChange={onPhotoChange} className="hidden" />
              </label>
              {photoPreview && (
                <div className="relative w-20 h-20 rounded-lg overflow-hidden border border-slate-700">
                   <img src={photoPreview} className="w-full h-full object-cover" />
                   <button onClick={() => {setPhoto(null); setPhotoPreview(null)}} className="absolute top-1 right-1 bg-black/50 text-white rounded-full p-0.5 hover:bg-rose-600"><XCircle size={14} /></button>
                </div>
              )}
            </div>
          </div>

          <div className="space-y-3 pt-2 text-left">
            <label className="block text-xs font-semibold text-slate-500 uppercase tracking-wider">Interactive Buttons (Max 3)</label>
            {buttons.map((b, i) => (
              <div key={i} className="flex gap-2">
                <input placeholder={`Btn ${i+1} Label`} value={b.label} onChange={e => updateButton(i, 'label', e.target.value)} className="flex-1 bg-slate-800/50 border border-slate-700/30 rounded-lg px-3 py-2 text-xs text-slate-300 outline-none focus:border-rose-500/50" />
                <input placeholder="URL (https://...)" value={b.url} onChange={e => updateButton(i, 'url', e.target.value)} className="flex-[2] bg-slate-800/50 border border-slate-700/30 rounded-lg px-3 py-2 text-xs text-slate-300 outline-none focus:border-rose-500/50" />
              </div>
            ))}
          </div>

          <button onClick={sendCustom} disabled={loading}
            className="w-full bg-gradient-to-r from-rose-600 to-rose-500 hover:from-rose-500 hover:to-rose-400 text-white py-3.5 rounded-xl font-bold text-sm shadow-lg shadow-rose-600/20 transition-all flex items-center justify-center gap-2 cursor-pointer disabled:opacity-50 mt-4">
            {loading ? <Loader className="animate-spin" size={18} /> : <Rocket size={18} />} Send Broadcast Now
          </button>
        </div>

        {/* Right: Preview (Mobile Style) */}
        <div className="flex flex-col items-center justify-center">
           <div className="w-[280px] bg-[#17212b] rounded-3xl overflow-hidden shadow-2xl border border-white/5 relative">
              <div className="bg-[#242f3d] p-3 text-white text-xs font-semibold flex items-center gap-2">
                <div className="w-6 h-6 rounded-full bg-blue-500/20 flex items-center justify-center overflow-hidden">
                  <Bot size={14} className="text-blue-400" />
                </div>
                <span>Sender Account Preview</span>
              </div>
              
              <div className="p-3 space-y-2">
                <div className="bg-[#182533] rounded-xl overflow-hidden self-end">
                   {photoPreview && <img src={photoPreview} className="w-full aspect-square object-cover opacity-90" />}
                   <div className="p-2.5 space-y-2 text-left">
                      <p className="text-xs text-[#e5e9ec] whitespace-pre-wrap leading-relaxed">{text || 'Message text will appear here...'}</p>
                      
                      {buttons.some(b => b.label) && (
                        <div className="grid grid-cols-1 gap-1.5 pt-1">
                          {buttons.map((b, i) => b.label && (
                             <div key={i} className="bg-[#2b5278] hover:bg-[#32608b] text-white text-[10px] py-1.5 rounded-md text-center font-medium flex items-center justify-center gap-1">
                                {b.label} <ExternalLink size={10} className="opacity-50" />
                             </div>
                          ))}
                        </div>
                      )}
                      
                      <div className="flex justify-end pt-1">
                         <span className="text-[9px] text-slate-500">{new Date().toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'})}</span>
                      </div>
                   </div>
                </div>
              </div>
           </div>
           <p className="text-[10px] text-slate-500 mt-4 text-center">This is an approximate visual preview of how <br/> the message will look in Telegram.</p>
        </div>
      </div>
    </div>
  )
}

/* ========== TEST & DEBUG TAB ========== */
function TestTab() {
  const [postLink, setPostLink] = useState('')
  const [targetGroup, setTargetGroup] = useState('')
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    axios.get(`${API}/forwarding-config`).then(r => {
      if (r.data) setPostLink(r.data.post_link || '')
    }).catch(() => {})
  }, [])

  const runTest = async () => {
    if(!postLink || !targetGroup) return toast.error('Fill both fields')
    setLoading(true)
    try {
      const res = await axios.post(`${API}/bot/test-forward`, { post_link: postLink, target_group: targetGroup })
      toast.success(res.data.message || 'Test Success!')
    } catch (e) { toast.error(e.response?.data?.detail || 'Test Failed') }
    finally { setLoading(false) }
  }

  const inputClass = "w-full bg-slate-800 border border-slate-700 rounded-xl px-4 py-3 text-slate-200 text-sm outline-none focus:border-emerald-500 transition-all"

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold text-white flex items-center gap-3">
            <CheckCircle className="text-emerald-400" size={24} /> Test & Debug
          </h2>
          <p className="text-slate-400 mt-1 text-sm">Send a single test message instantly to verify your setup without starting the hourly bot.</p>
        </div>
      </div>
      
      <div className="bg-slate-900/40 rounded-2xl border border-slate-700/50 p-6 space-y-4 max-w-2xl">
        <div>
          <label className="block text-xs font-semibold text-slate-500 mb-2 uppercase tracking-wider">Telegram Post Link</label>
          <input type="text" value={postLink} onChange={e => setPostLink(e.target.value)}
            className={inputClass} placeholder="https://t.me/imesh_cloud_official/16" />
        </div>
        <div>
          <label className="block text-xs font-semibold text-slate-500 mb-2 uppercase tracking-wider">Test Target Group (@username or link)</label>
          <input type="text" value={targetGroup} onChange={e => setTargetGroup(e.target.value)}
            placeholder="@my_test_group" className={inputClass} />
        </div>
        <button onClick={runTest} disabled={loading}
          className="bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 text-white px-6 py-3.5 rounded-xl font-medium w-full flex justify-center items-center gap-3 transition-colors mt-4">
          {loading ? <Loader className="animate-spin" size={20} /> : <Play size={20} />} Send Test Forward
        </button>
      </div>
    </div>
  )
}

/* ========== STATUS TAB ========== */
function StatusTab({ logs, refreshLogs }) {
  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold text-white flex items-center gap-3">
            <Activity className="text-emerald-400" size={24} /> Live Status & Logs
          </h2>
          <p className="text-slate-400 mt-1 text-sm">Real-time bot activity</p>
        </div>
        <button onClick={refreshLogs} className="flex items-center gap-2 text-slate-400 hover:text-white border border-slate-700 px-4 py-2 rounded-lg text-sm transition-all hover:border-slate-500 cursor-pointer">
          <RefreshCw size={14} /> Refresh
        </button>
      </div>

      <div className="bg-slate-950/70 border border-slate-800 rounded-2xl p-5 min-h-[420px] font-mono text-xs space-y-1.5 overflow-y-auto max-h-[550px]">
        {logs.length === 0 ? (
          <p className="text-slate-600 text-center mt-16">No logs yet. Start the bot to see activity.</p>
        ) : logs.map((log, i) => (
          <div key={i} className={`flex gap-3 items-start ${
            log.type === 'success' ? 'text-emerald-400' :
            log.type === 'error' ? 'text-red-400' :
            log.type === 'warn' ? 'text-amber-400' : 'text-slate-400'
          }`}>
            <span className="text-slate-600 shrink-0">{log.time}</span>
            <span>{log.message}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

/* ========== MAIN APP ========== */
function App() {
  const [activeTab, setActiveTab] = useState('settings')
  const [botStatus, setBotStatus] = useState('stopped')
  const [logs, setLogs] = useState([])

  useEffect(() => {
    // Initial status check
    axios.get(`${API}/bot/status`).then(r => {
      setBotStatus(r.data.status)
    }).catch(() => {})

    // Auto refresh logs when tab is status
    const interval = setInterval(() => {
      refreshLogs()
      // Also occasionally sync status
      axios.get(`${API}/bot/status`).then(r => setBotStatus(r.data.status)).catch(() => {})
    }, 5000)
    return () => clearInterval(interval)
  }, [])

  const addLog = (message, type = 'info') => {
    const time = new Date().toLocaleTimeString()
    setLogs(p => [...p, { message, type, time }])
  }

  const refreshLogs = async () => {
    try {
      const r = await axios.get(`${API}/logs`)
      setLogs(r.data.logs || [])
    } catch { addLog('Could not fetch logs', 'error') }
  }

  const startBot = async () => {
    try {
      await axios.post(`${API}/bot/start`)
      setBotStatus('running')
      addLog('Bot started!', 'success')
      toast.success('Bot is running!')
    } catch (e) {
      const msg = e.response?.data?.detail || 'Failed'
      addLog(msg, 'error')
      toast.error(msg)
    }
  }

  const stopBot = async () => {
    try {
      await axios.post(`${API}/bot/stop`)
      setBotStatus('stopped')
      addLog('Bot stopped.', 'warn')
      toast('Bot stopped', { icon: '🛑' })
    } catch { toast.error('Failed to stop') }
  }

  return (
    <div className="min-h-screen flex bg-slate-900">
      <Toaster position="top-right" toastOptions={{ style: { background: '#1e293b', color: '#f1f5f9', border: '1px solid #334155' } }} />
      <div className="fixed inset-0 pointer-events-none overflow-hidden">
        <div className="absolute -top-32 -left-32 w-96 h-96 bg-blue-600/10 rounded-full blur-3xl"></div>
        <div className="absolute bottom-0 right-0 w-96 h-96 bg-indigo-600/10 rounded-full blur-3xl"></div>
      </div>

      <Sidebar activeTab={activeTab} setActiveTab={setActiveTab} botStatus={botStatus} onStart={startBot} onStop={stopBot} />

      <main className="flex-1 p-8 relative z-10">
        <div className="max-w-4xl mx-auto p-8 min-h-[calc(100vh-4rem)]" style={{ ...glassStyle, boxShadow: '0 25px 50px rgba(0,0,0,0.3)' }}>
          {activeTab === 'settings' && <SettingsTab />}
          {activeTab === 'groups' && <GroupsTab />}
          {activeTab === 'autojoin' && <AutoJoinTab />}
          {activeTab === 'custom' && <CustomBroadcastTab />}
          {activeTab === 'test' && <TestTab />}
          {activeTab === 'status' && <StatusTab logs={logs} refreshLogs={refreshLogs} />}
        </div>
      </main>
    </div>
  )
}

export default App
