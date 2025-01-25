import kete


__all__ = []


def jnow(self, jd=None):
    """
    Convert a Vector into the Equinox of Date (EOD) equatorial frame.
    IE: The current equatorial axis of Earth.
    """
    if jd is None:
        jd = kete.Time.now().jd
    else:
        jd = kete.Time(jd).jd
    rot = np.transpose(kete.conversion.earth_precession_rotation(jd))
    return self.as_equatorial.Vector(rot @ vec, kete.Frames.Equatorial)

# monkey patch Vector to use this
kete.Vector.jnow = jnow