

def eng(value):
    "return a user-friendly string reprenting `value'"

    assert value>=0

    if value < 5:
        res = f'{value:.2f}'
    elif value<1000:
        res=f'{value:.0f}'
    elif value<10000:
        res=f'{value/1000:.1f}k'.replace('.0','')
    elif value<1e6:
        res=f'{value/1000:.0f}k'
    elif value<10e6:
        res=f'{value/1e6:.1f}M'.replace('.0','')
    elif value<1e9:
        res=f'{value/1e6:.0f}M'
    elif value<1e12:
        res=f'{value/1e9:.0f}G'
    else:
        res="huge lol"
    assert len(res) <= 4
    # print(res,value)
    return res



def time2s(seconds):
    """return a user-friendy string representation for a given duration"""
    if seconds<5:
        return f'{seconds:.2f}s'
    if seconds<10:
        return f'{seconds:.1f}s'
    if seconds<60:
        return str(int(seconds))+'s'

    mins, secs = int(seconds/60), int(seconds % 60)

    if mins<3:
        return str(mins)+'m'+time2s(secs)
        
    if mins<10:
        if   secs < 15:
            return str(mins)+'m'
        elif secs > 45:
            return str(mins+1)+'m'
        str(mins)+'m'+time2s(secs)

    hours, mins = int(seconds/3600), int((seconds % 3600)/60)

    if hours==0:
        return str(mins)+'m'

    if mins < 15:
        return str(hours)+'h'
    if mins > 45:
        return str(hours+1)+'h'
    return str(hours)+'h'+str(mins)+'m'
        
