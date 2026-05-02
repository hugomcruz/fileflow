import { useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { Zap, CheckCircle } from 'lucide-react';
import api from '../services/api';
import { useAuth } from '../context/AuthContext';

const ERROR_MESSAGES: Record<string, string> = {
  auth_failed: 'Authentication failed. Please try again.',
  invalid_state: 'Security check failed. Please try again.',
  profile_failed: 'Could not load your profile. Please try again.',
};

type Mode = 'signin' | 'signup';

export default function Login() {
  const [params] = useSearchParams();
  const [mode, setMode] = useState<Mode>('signin');
  const error = params.get('error');

  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [registered, setRegistered] = useState(false);

  const { login } = useAuth();
  const navigate = useNavigate();
  const switchMode = (next: Mode) => {
    setMode(next);
    setFormError(null);
    setRegistered(false);
    setName('');
    setEmail('');
    setPassword('');
  };

  const handleGoogle = () => { window.location.href = '/api/auth/google'; };
  const handleMicrosoft = () => { window.location.href = '/api/auth/microsoft'; };
  const handleApple = () => { window.location.href = '/api/auth/apple'; };

  const handleEmailSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setFormError(null);
    setIsSubmitting(true);
    try {
      if (mode === 'signup') {
        await api.post('/auth/register', { name, email, password });
        setRegistered(true);
        setMode('signin');
        setName('');
        setPassword('');
      } else {
        const res = await api.post<{ token: string }>('/auth/login', { email, password });
        await login(res.data.token);
        navigate('/dashboard', { replace: true });
      }
    } catch (err: any) {
      const detail = err.response?.data?.detail;
      if (Array.isArray(detail)) {
        // FastAPI 422 validation errors
        setFormError(detail.map((e: any) => e.msg).join(' · '));
      } else {
        setFormError(detail ?? 'Something went wrong. Please try again.');
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  const isSignIn = mode === 'signin';

  return (
    <div className="min-h-screen flex">
      {/* ── Left hero panel ───────────────────────────────────────── */}
      <div className="hidden lg:flex lg:w-1/2 relative bg-gradient-to-br from-primary-950 via-primary-900 to-indigo-800 flex-col justify-between p-12 overflow-hidden">
        {/* Decorative blobs */}
        <div className="absolute -top-32 -left-32 w-96 h-96 bg-indigo-500 opacity-20 rounded-full blur-3xl" />
        <div className="absolute bottom-0 right-0 w-80 h-80 bg-primary-400 opacity-10 rounded-full blur-3xl" />
        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-64 h-64 bg-white opacity-5 rounded-full blur-2xl" />

        {/* Logo */}
        <div className="relative flex items-center gap-3">
          <div className="flex items-center justify-center w-10 h-10 rounded-xl bg-white/10 backdrop-blur shadow">
            <Zap className="w-5 h-5 text-white" />
          </div>
          <span className="text-white text-xl font-bold tracking-tight">FileFlow</span>
        </div>

        {/* Hero copy */}
        <div className="relative space-y-6">
          <h2 className="text-4xl font-extrabold text-white leading-tight">
            Your files,<br />beautifully organised.
          </h2>
          <p className="text-primary-200 text-lg leading-relaxed max-w-sm">
            Automatically rename and organise your photos and videos across OneDrive and Dropbox — using EXIF timestamps and smart scheduling.
          </p>

          {/* Feature pills */}
          <div className="flex flex-wrap gap-3 pt-2">
            {['OneDrive', 'Dropbox', 'EXIF Metadata', 'Smart Scheduling'].map((f) => (
              <span key={f} className="px-3 py-1 rounded-full bg-white/10 text-white/80 text-xs font-medium backdrop-blur border border-white/10">
                {f}
              </span>
            ))}
          </div>
        </div>

        {/* Bottom tagline */}
        <p className="relative text-primary-400 text-sm">
          © {new Date().getFullYear()} FileFlow · All files stay yours.
        </p>
      </div>

      {/* ── Right auth panel ──────────────────────────────────────── */}
      <div className="flex-1 flex flex-col items-center justify-center bg-white px-6 py-12 lg:px-16">
        {/* Mobile logo */}
        <div className="lg:hidden flex items-center gap-2 mb-10">
          <div className="flex items-center justify-center w-9 h-9 rounded-xl bg-primary-600">
            <Zap className="w-5 h-5 text-white" />
          </div>
          <span className="text-primary-900 text-xl font-bold tracking-tight">FileFlow</span>
        </div>

        <div className="w-full max-w-sm">
          {/* Heading */}
          <div className="mb-8">
            <h1 className="text-2xl font-bold text-slate-900">
              {isSignIn ? 'Sign in to FileFlow' : 'Create your account'}
            </h1>
            <p className="mt-1 text-slate-500 text-sm">
              {isSignIn
                ? 'Welcome back! Choose how you want to sign in.'
                : 'Get started for free. No credit card required.'}
            </p>
          </div>

          {/* Registration success banner */}
          {registered && (
            <div className="mb-6 px-4 py-3 rounded-xl bg-green-50 border border-green-200 text-green-700 text-sm flex items-center gap-2">
              <CheckCircle className="w-4 h-4 flex-shrink-0" />
              Account created! Sign in with your new credentials.
            </div>
          )}

          {/* Error banner */}
          {error && (
            <div className="mb-6 px-4 py-3 rounded-xl bg-red-50 border border-red-200 text-red-700 text-sm">
              {ERROR_MESSAGES[error] ?? 'Something went wrong. Please try again.'}
            </div>
          )}

          {/* OAuth buttons */}
          <div className="flex flex-col gap-3">
            <OAuthButton icon={<GoogleIcon />} onClick={handleGoogle}>
              {isSignIn ? 'Sign in with Google' : 'Sign up with Google'}
            </OAuthButton>

            <OAuthButton icon={<MicrosoftIcon />} onClick={handleMicrosoft}>
              {isSignIn ? 'Sign in with Microsoft' : 'Sign up with Microsoft'}
            </OAuthButton>

            <OAuthButton icon={<AppleIcon />} onClick={handleApple}>
              {isSignIn ? 'Sign in with Apple' : 'Sign up with Apple'}
            </OAuthButton>
          </div>

          {/* Divider */}
          <div className="flex items-center gap-3 my-6">
            <div className="flex-1 h-px bg-slate-200" />
            <span className="text-slate-400 text-xs">or continue with email</span>
            <div className="flex-1 h-px bg-slate-200" />
          </div>

          {/* Email form error */}
          {formError && (
            <div className="mb-3 px-4 py-3 rounded-xl bg-red-50 border border-red-200 text-red-700 text-sm">
              {formError}
            </div>
          )}

          {/* Email / password form */}
          <form onSubmit={handleEmailSubmit} className="flex flex-col gap-3">
            {!isSignIn && (
              <input
                type="text"
                placeholder="Full name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                required
                className="w-full px-4 py-3 rounded-xl border border-slate-200 text-sm text-slate-800 placeholder-slate-400
                           focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-transparent transition"
              />
            )}
            <input
              type="email"
              placeholder="Email address"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              className="w-full px-4 py-3 rounded-xl border border-slate-200 text-sm text-slate-800 placeholder-slate-400
                         focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-transparent transition"
            />
            <input
              type="password"
              placeholder="Password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              className="w-full px-4 py-3 rounded-xl border border-slate-200 text-sm text-slate-800 placeholder-slate-400
                         focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-transparent transition"
            />
            <button
              type="submit"
              disabled={isSubmitting}
              className="w-full py-3 px-4 rounded-xl bg-primary-600 text-white font-semibold text-sm
                         hover:bg-primary-700 active:bg-primary-800 disabled:opacity-50 disabled:cursor-not-allowed
                         transition-colors"
            >
              {isSubmitting ? 'Please wait…' : isSignIn ? 'Sign in' : 'Create account'}
            </button>
          </form>

          {/* Toggle sign in / sign up */}
          <p className="text-center text-sm text-slate-500 mt-4">
            {isSignIn ? "Don't have an account? " : 'Already have an account? '}
            <button
              onClick={() => switchMode(isSignIn ? 'signup' : 'signin')}
              className="text-primary-600 font-semibold hover:underline"
            >
              {isSignIn ? 'Sign up' : 'Sign in'}
            </button>
          </p>

          {/* Legal */}
          <p className="mt-8 text-center text-xs text-slate-400">
            By continuing you agree to our{' '}
            <span className="underline cursor-pointer hover:text-slate-600">Terms of Service</span>{' '}
            and{' '}
            <span className="underline cursor-pointer hover:text-slate-600">Privacy Policy</span>.
          </p>
        </div>
      </div>
    </div>
  );
}

// ── Shared OAuth button ────────────────────────────────────────────────────────
function OAuthButton({
  icon,
  onClick,
  disabled = false,
  children,
}: {
  icon: React.ReactNode;
  onClick?: () => void;
  disabled?: boolean;
  children: React.ReactNode;
}) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className="flex items-center gap-3 w-full px-4 py-3.5 rounded-xl border border-slate-200
                 bg-white text-sm font-medium text-slate-700 shadow-sm
                 hover:bg-slate-50 hover:border-slate-300 active:bg-slate-100
                 disabled:opacity-40 disabled:cursor-not-allowed
                 transition-all duration-150"
    >
      <span className="flex-shrink-0">{icon}</span>
      <span className="flex-1 text-left">{children}</span>
    </button>
  );
}

// ── Icons ──────────────────────────────────────────────────────────────────────
function GoogleIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 18 18" fill="none" xmlns="http://www.w3.org/2000/svg">
      <path d="M17.64 9.205c0-.639-.057-1.252-.164-1.841H9v3.481h4.844a4.14 4.14 0 01-1.796 2.716v2.259h2.908c1.702-1.567 2.684-3.875 2.684-6.615z" fill="#4285F4"/>
      <path d="M9 18c2.43 0 4.467-.806 5.956-2.18l-2.908-2.259c-.806.54-1.837.86-3.048.86-2.344 0-4.328-1.584-5.036-3.711H.957v2.332A8.997 8.997 0 009 18z" fill="#34A853"/>
      <path d="M3.964 10.71A5.41 5.41 0 013.682 9c0-.593.102-1.17.282-1.71V4.958H.957A8.996 8.996 0 000 9c0 1.452.348 2.827.957 4.042l3.007-2.332z" fill="#FBBC05"/>
      <path d="M9 3.58c1.321 0 2.508.454 3.44 1.345l2.582-2.58C13.463.891 11.426 0 9 0A8.997 8.997 0 00.957 4.958L3.964 7.29C4.672 5.163 6.656 3.58 9 3.58z" fill="#EA4335"/>
    </svg>
  );
}

function MicrosoftIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 18 18" fill="none" xmlns="http://www.w3.org/2000/svg">
      <rect x="1" y="1" width="7.5" height="7.5" fill="#F25022"/>
      <rect x="9.5" y="1" width="7.5" height="7.5" fill="#7FBA00"/>
      <rect x="1" y="9.5" width="7.5" height="7.5" fill="#00A4EF"/>
      <rect x="9.5" y="9.5" width="7.5" height="7.5" fill="#FFB900"/>
    </svg>
  );
}

function AppleIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 18 18" fill="none" xmlns="http://www.w3.org/2000/svg">
      <path d="M14.05 9.57c-.02-2.07 1.69-3.07 1.77-3.12-0.97-1.41-2.47-1.6-3-1.63-1.27-.13-2.49.75-3.14.75-.65 0-1.64-.73-2.7-.71C5.5 4.88 4 5.85 3.17 7.34c-1.69 2.92-.43 7.24 1.2 9.61.8 1.16 1.76 2.46 3.01 2.41 1.21-.05 1.67-.78 3.13-.78 1.46 0 1.87.78 3.14.75 1.3-.02 2.13-1.18 2.92-2.34.93-1.34 1.31-2.64 1.33-2.71-.03-.01-2.53-.97-2.55-3.71zM11.86 3.34c.67-.81 1.12-1.93.99-3.05-.96.04-2.12.64-2.81 1.45-.61.7-1.15 1.84-.99 2.92 1.07.08 2.15-.54 2.81-1.32z" fill="#000"/>
    </svg>
  );
}
